from datetime import timedelta

from lxml import html as lxml_html
from markupsafe import Markup

from odoo import api, fields, models, tools
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import html_sanitize, is_html_empty

TICKET_PRIORITY = [
    ('0', 'Low'),
    ('1', 'Medium'),
    ('2', 'High'),
    ('3', 'Urgent'),
]


class OmHelpdeskTicket(models.Model):
    _name = 'om.helpdesk.ticket'
    _description = 'Helpdesk Ticket'
    _inherit = ['portal.mixin', 'mail.activity.mixin', 'rating.mixin']
    _order = 'priority desc, id desc'
    _primary_email = 'email_from'
    _mail_post_access = 'read'
    _check_company_auto = True

    def _default_team_id(self):
        team_id = self.env.context.get('default_team_id')
        if team_id:
            return self.env['om.helpdesk.team'].browse(team_id)
        return self.env['om.helpdesk.team'].search(
            [('member_ids', 'in', self.env.uid), ('company_id', 'in', self.env.companies.ids)], limit=1
        ) or self.env['om.helpdesk.team'].search([('company_id', 'in', self.env.companies.ids)], limit=1)

    number = fields.Char(string='Ticket Number', readonly=True, copy=False, index='trigram', default='/')
    name = fields.Char(string='Subject', required=True, tracking=True, index='trigram')
    description = fields.Html()
    active = fields.Boolean(default=True)
    team_id = fields.Many2one(
        'om.helpdesk.team', string='Team', index=True, tracking=True, check_company=True,
        default=_default_team_id)
    user_id = fields.Many2one(
        'res.users', string='Assigned To', index=True, tracking=True, check_company=True,
        compute='_compute_user_id', store=True, readonly=False,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]")
    partner_id = fields.Many2one('res.partner', string='Customer', index=True, tracking=True, check_company=True)
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', store=True, index=True, string='Customer Company')
    partner_name = fields.Char(string='Customer Name', compute='_compute_partner_name', store=True, readonly=False)
    email_from = fields.Char(string='Email', compute='_compute_email_from', store=True, readonly=False, index='trigram')
    partner_phone = fields.Char(string='Phone', compute='_compute_partner_phone', store=True, readonly=False)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        compute='_compute_company_id', store=True, readonly=False,
        default=lambda self: self.env.company)
    priority = fields.Selection(TICKET_PRIORITY, default='0', index=True, tracking=True)
    ticket_type_id = fields.Many2one('om.helpdesk.ticket.type', string='Type', tracking=True)
    tag_ids = fields.Many2many('om.helpdesk.tag', string='Tags')
    stage_id = fields.Many2one(
        'om.helpdesk.stage', string='Stage', index=True, tracking=True, copy=False, ondelete='restrict',
        compute='_compute_stage_id', store=True, readonly=False, group_expand='_read_group_stage_ids',
        domain="[('team_ids', 'in', team_id)]")
    is_closed = fields.Boolean(related='stage_id.is_close', store=True, string='Closed', index=True)
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked'),
    ], string='Status', default='normal', required=True, copy=False, tracking=True)
    legend_blocked = fields.Char(related='stage_id.legend_blocked', string='Kanban Blocked')
    legend_done = fields.Char(related='stage_id.legend_done', string='Kanban Ready')
    legend_normal = fields.Char(related='stage_id.legend_normal', string='Kanban Ongoing')
    color = fields.Integer(string='Color Index')
    close_reason_id = fields.Many2one('om.helpdesk.close.reason', string='Close Reason', tracking=True)
    privacy_visibility = fields.Selection(related='team_id.privacy_visibility', string='Team Visibility')
    use_sla = fields.Boolean(related='team_id.use_sla', string='Team Uses SLA')
    use_rating = fields.Boolean(related='team_id.use_rating', string='Team Uses Ratings')

    date_open = fields.Datetime(string='Opened On', default=fields.Datetime.now, readonly=True, copy=False, index=True)
    date_assign = fields.Datetime(string='Assigned On', compute='_compute_date_assign', store=True, copy=False)
    date_first_response = fields.Datetime(string='First Response On', readonly=True, copy=False)
    date_closed = fields.Datetime(string='Closed On', compute='_compute_date_closed', store=True, copy=False, index=True)
    date_last_stage_update = fields.Datetime(string='Last Stage Update', default=fields.Datetime.now, copy=False, readonly=True)
    hours_to_assign = fields.Float(string='Hours to Assign', compute='_compute_durations', store=True, aggregator='avg')
    hours_to_first_response = fields.Float(string='Hours to First Response', compute='_compute_durations', store=True, aggregator='avg')
    hours_to_close = fields.Float(string='Hours to Close', compute='_compute_durations', store=True, aggregator='avg')
    open_hours = fields.Float(string='Open Time (Hours)', compute='_compute_open_hours')

    sla_status_ids = fields.One2many('om.helpdesk.sla.status', 'ticket_id', string='SLA Status')
    sla_deadline = fields.Datetime(
        string='SLA Deadline', compute='_compute_sla_info', store=True, index=True,
        help="Nearest deadline among the SLAs not reached yet.")
    sla_fail = fields.Boolean(string='SLA Failed', compute='_compute_sla_info', store=True, index=True)
    sla_success = fields.Boolean(string='SLA Reached', compute='_compute_sla_info', store=True,
                                 help="All SLAs of the ticket are reached in time.")
    sla_state = fields.Selection([
        ('none', 'No SLA'),
        ('ongoing', 'On Time'),
        ('reached', 'Reached'),
        ('failed', 'Failed'),
    ], string='SLA', compute='_compute_sla_info', store=True)
    merged_into_id = fields.Many2one('om.helpdesk.ticket', string='Merged Into', readonly=True, copy=False, index='btree_not_null')

    # ------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------

    @api.depends('partner_id')
    def _compute_partner_name(self):
        for ticket in self:
            if ticket.partner_id:
                ticket.partner_name = ticket.partner_id.name

    @api.depends('partner_id')
    def _compute_email_from(self):
        for ticket in self:
            if ticket.partner_id.email:
                ticket.email_from = ticket.partner_id.email

    @api.depends('partner_id')
    def _compute_partner_phone(self):
        for ticket in self:
            if ticket.partner_id.phone:
                ticket.partner_phone = ticket.partner_id.phone

    @api.depends('team_id')
    def _compute_company_id(self):
        for ticket in self:
            if ticket.team_id:
                ticket.company_id = ticket.team_id.company_id
            elif not ticket.company_id:
                ticket.company_id = self.env.company

    @api.depends('team_id')
    def _compute_stage_id(self):
        for ticket in self:
            if ticket.team_id:
                if not ticket.stage_id or ticket.team_id not in ticket.stage_id.team_ids:
                    ticket.stage_id = ticket._stage_find(ticket.team_id.id)
            elif not ticket.stage_id:
                ticket.stage_id = ticket._stage_find(False)

    @api.depends('team_id')
    def _compute_user_id(self):
        for ticket in self:
            if ticket.user_id and ticket.team_id and ticket.team_id.member_ids \
                    and ticket.user_id not in ticket.team_id.member_ids | ticket.team_id.user_id:
                ticket.user_id = False

    @api.depends('user_id')
    def _compute_date_assign(self):
        for ticket in self:
            ticket.date_assign = fields.Datetime.now() if ticket.user_id else False

    @api.depends('stage_id', 'is_closed')
    def _compute_date_closed(self):
        for ticket in self:
            if ticket.is_closed:
                if not ticket.date_closed:
                    ticket.date_closed = fields.Datetime.now()
            else:
                ticket.date_closed = False

    @api.depends('date_open', 'date_assign', 'date_first_response', 'date_closed')
    def _compute_durations(self):
        def hours(start, end):
            return max((end - start).total_seconds() / 3600, 0.0) if start and end else 0.0

        for ticket in self:
            ticket.hours_to_assign = hours(ticket.date_open, ticket.date_assign)
            ticket.hours_to_first_response = hours(ticket.date_open, ticket.date_first_response)
            ticket.hours_to_close = hours(ticket.date_open, ticket.date_closed)

    def _compute_open_hours(self):
        now = fields.Datetime.now()
        for ticket in self:
            end = ticket.date_closed or now
            ticket.open_hours = (end - ticket.date_open).total_seconds() / 3600 if ticket.date_open else 0.0

    @api.depends('sla_status_ids.status', 'sla_status_ids.deadline')
    def _compute_sla_info(self):
        for ticket in self:
            lines = ticket.sla_status_ids
            ongoing = lines.filtered(lambda line: not line.reached_datetime and line.deadline)
            ticket.sla_deadline = min(ongoing.mapped('deadline')) if ongoing else False
            ticket.sla_fail = any(line.status == 'failed' for line in lines)
            ticket.sla_success = bool(lines) and all(line.status == 'reached' for line in lines)
            if not lines:
                ticket.sla_state = 'none'
            elif ticket.sla_fail:
                ticket.sla_state = 'failed'
            elif ticket.sla_success:
                ticket.sla_state = 'reached'
            else:
                ticket.sla_state = 'ongoing'

    def _compute_access_url(self):
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = f'/my/tickets/{ticket.id}'

    @api.depends('number', 'name')
    def _compute_display_name(self):
        for ticket in self:
            ticket.display_name = f'{ticket.name} (#{ticket.number})' if ticket.number and ticket.number != '/' else ticket.name

    @api.model
    def _search_display_name(self, operator, value):
        if operator in ('ilike', 'like', '=', '=like', '=ilike', 'not ilike') and isinstance(value, str):
            value = value.lstrip('#')
            positive = Domain('name', operator, value) | Domain('number', operator, value)
            return positive if operator != 'not ilike' else Domain('name', operator, value) & Domain('number', operator, value)
        return super()._search_display_name(operator, value)

    # ------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------

    def _stage_find(self, team_id, domain=None):
        search_domain = Domain('team_ids', 'in', [team_id]) if team_id else Domain.TRUE
        if domain:
            search_domain &= Domain(domain)
        return self.env['om.helpdesk.stage'].search(search_domain, order='sequence, id', limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        team_id = self.env.context.get('default_team_id')
        search_domain = Domain('id', 'in', stages.ids)
        if team_id:
            search_domain |= Domain('team_ids', 'in', [team_id])
        return stages.search(search_domain, order=stages._order)

    def _get_closing_stage(self):
        self.ensure_one()
        stages = self.team_id.stage_ids if self.team_id else self.env['om.helpdesk.stage'].search([])
        return stages.filtered('is_close').sorted(lambda s: (s.sequence, s.id))[:1]

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if not vals.get('number') or vals['number'] == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['number'] = self.env['ir.sequence'].with_company(company).next_by_code('om.helpdesk.ticket') or '/'
            if not vals.get('partner_id') and vals.get('email_from'):
                vals['partner_id'] = self._find_or_create_partner(vals['email_from'], vals.get('partner_name'), vals.get('partner_phone')).id
            team_id = vals.get('team_id') or self.env.context.get('default_team_id')
            if team_id and not vals.get('user_id'):
                team = self.env['om.helpdesk.team'].browse(team_id)
                user = team._get_new_ticket_user()
                if user:
                    vals['user_id'] = user.id
            vals.setdefault('date_last_stage_update', now)
        tickets = super().create(vals_list)
        tickets._sla_apply()
        for ticket in tickets.filtered('partner_id'):
            if ticket.partner_id not in ticket.message_partner_ids:
                ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
        if not self.env.context.get('mail_notrack'):
            # the email template of the first stage, e.g. "we received your request"
            for ticket in tickets.filtered(lambda t: t.stage_id.template_id and t.partner_id):
                ticket._track_post_template(['stage_id'])
        return tickets

    def write(self, vals):
        if 'stage_id' in vals:
            vals.setdefault('date_last_stage_update', fields.Datetime.now())
            if 'kanban_state' not in vals:
                vals['kanban_state'] = 'normal'
        old_closed = {ticket.id: ticket.is_closed for ticket in self} if 'stage_id' in vals else {}
        res = super().write(vals)
        if set(vals) & {'team_id', 'priority', 'ticket_type_id', 'tag_ids', 'partner_id'}:
            self._sla_apply(keep_reached=True)
        if 'stage_id' in vals:
            self._sla_reach()
            newly_closed = self.filtered(lambda t: t.is_closed and not old_closed.get(t.id))
            newly_closed._send_rating_request()
        if vals.get('partner_id'):
            for ticket in self:
                if ticket.partner_id not in ticket.message_partner_ids:
                    ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
        return res

    @api.model
    def _find_or_create_partner(self, email, name=None, phone=None):
        """ Partner of a ticket coming from an email or a form: matched by email, created if unknown. """
        normalized = tools.email_normalize(email)
        if not normalized:
            return self.env['res.partner']
        partner = self.env['res.partner'].sudo().search([('email_normalized', '=', normalized)], limit=1)
        if not partner:
            partner = self.env['res.partner'].sudo().create({
                'name': name or tools.parse_contact_from_email(email)[0] or normalized,
                'email': normalized,
                'phone': phone or False,
            })
        return partner

    # ------------------------------------------------------------
    # SLA
    # ------------------------------------------------------------

    def _sla_apply(self, keep_reached=False):
        """ Create the SLA status lines of the policies matching each ticket and remove the
        lines of policies that do not match anymore (reached lines are kept on update). """
        Status = self.env['om.helpdesk.sla.status'].sudo()
        to_create = []
        for ticket in self:
            if not ticket.team_id or not ticket.team_id.use_sla:
                ticket.sla_status_ids.filtered(lambda line: not line.reached_datetime).sudo().unlink()
                continue
            slas = ticket.team_id.sudo().sla_ids.filtered(lambda sla: sla._applies_to(ticket))
            lines = ticket.sudo().sla_status_ids
            obsolete = lines.filtered(lambda line: line.sla_id not in slas and not (keep_reached and line.reached_datetime))
            obsolete.unlink()
            existing = lines.exists().mapped('sla_id')
            start = ticket.date_open or fields.Datetime.now()
            stage_seq = ticket.stage_id.sequence
            for sla in slas - existing:
                reached = ticket.date_last_stage_update if ticket.stage_id and stage_seq >= sla.stage_id.sequence else False
                to_create.append({
                    'ticket_id': ticket.id,
                    'sla_id': sla.id,
                    'deadline': sla._compute_deadline(start),
                    'reached_datetime': reached,
                })
        if to_create:
            Status.create(to_create)

    def _sla_reach(self):
        """ Mark the SLAs whose target stage is reached, and reopen them when the ticket goes back. """
        now = fields.Datetime.now()
        for ticket in self:
            seq = ticket.stage_id.sequence
            for line in ticket.sudo().sla_status_ids:
                target_seq = line.sla_id.stage_id.sequence
                if seq >= target_seq and not line.reached_datetime:
                    line.reached_datetime = now
                elif seq < target_seq and line.reached_datetime and not ticket.is_closed:
                    line.reached_datetime = False

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_assign_to_me(self):
        self.write({'user_id': self.env.uid})

    def action_close(self):
        for ticket in self:
            stage = ticket._get_closing_stage()
            if not stage:
                raise UserError(self.env._("The team of ticket %s has no closing stage.", ticket.display_name))
            ticket.stage_id = stage

    def action_open_merge(self):
        return {
            'name': self.env._('Merge Tickets'),
            'type': 'ir.actions.act_window',
            'res_model': 'om.helpdesk.ticket.merge',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_ids': self.ids},
        }

    def action_open_ratings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_rating')
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id), ('consumed', '=', True)]
        return action

    def action_open_partner_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_ticket')
        action['domain'] = [('commercial_partner_id', '=', self.commercial_partner_id.id)]
        action['context'] = {'default_partner_id': self.partner_id.id}
        action['display_name'] = self.env._('Tickets of %s', self.commercial_partner_id.display_name)
        return action

    # ------------------------------------------------------------
    # Rating
    # ------------------------------------------------------------

    def _send_rating_request(self):
        template = self.env.ref('om_helpdesk.mail_template_ticket_rating', raise_if_not_found=False)
        if not template:
            return
        for ticket in self:
            partner = ticket.partner_id
            if ticket.team_id.use_rating and partner and partner != self.env.user.partner_id:
                ticket.rating_send_request(template, lang=partner.lang, force_send=False)

    def _rating_get_parent_field_name(self):
        return 'team_id'

    def _rating_apply_get_default_subtype_id(self):
        return self.env['ir.model.data']._xmlid_to_res_id('om_helpdesk.mt_ticket_rated')

    def rating_get_portal_token(self):
        """ Token for the rating smileys shown on the portal page of a closed ticket. """
        self.ensure_one()
        return self._rating_get_access_token(self.partner_id)

    # ------------------------------------------------------------
    # Mail
    # ------------------------------------------------------------

    def _creation_subtype(self):
        return self.env.ref('om_helpdesk.mt_ticket_new')

    def _creation_message(self):
        self.ensure_one()
        if self.team_id:
            return self.env._('Ticket created in the %(team)s team.', team=self.team_id.display_name)
        return self.env._('Ticket created.')

    def _track_log_get_default_subtype(self, track_init_values):
        self.ensure_one()
        if 'stage_id' in track_init_values:
            return self.env.ref('om_helpdesk.mt_ticket_stage')
        return super()._track_log_get_default_subtype(track_init_values)

    def _track_template_parameters(self, tracked_fields):
        res = super()._track_template_parameters(tracked_fields)
        ticket = self[0]
        if 'stage_id' in tracked_fields and ticket.exists() and ticket.stage_id.template_id:
            res['stage_id'] = (ticket.stage_id.template_id, {
                'auto_delete_keep_log': False,
                'subtype_id': self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note'),
                'email_layout_xmlid': 'mail.mail_notification_light',
            })
        return res

    def _mail_get_message_subtypes(self):
        res = super()._mail_get_message_subtypes()
        if len(self) == 1 and not self.team_id.use_rating:
            res -= self.env.ref('om_helpdesk.mt_ticket_rated')
        return res

    def _notify_get_reply_to(self, default=None, author_id=False):
        aliases = self.sudo().mapped('team_id')._notify_get_reply_to(default=default, author_id=author_id)
        res = {ticket.id: aliases.get(ticket.team_id.id) for ticket in self}
        leftover = self.filtered(lambda rec: not rec.team_id)
        if leftover:
            res.update(super(OmHelpdeskTicket, leftover)._notify_get_reply_to(default=default, author_id=author_id))
        return res

    def _notify_get_recipients_groups(self, message, model_description):
        groups = super()._notify_get_recipients_groups(message, model_description)
        if not self:
            return groups
        self.ensure_one()
        portal_ok = self.team_id.privacy_visibility == 'portal'
        for group_name, _group_method, group_data in groups:
            if group_name in ('portal', 'portal_customer'):
                group_data['has_button_access'] = portal_ok
        return groups

    def _get_customer_information(self):
        email_keys_to_values = super()._get_customer_information()
        for ticket in self:
            email_key = tools.email_normalize(ticket.email_from) or ticket.email_from
            if email_key and not ticket.partner_id:
                email_keys_to_values.setdefault(email_key, {}).update({
                    'name': ticket.partner_name or tools.parse_contact_from_email(ticket.email_from)[0] or ticket.email_from,
                    'phone': ticket.partner_phone,
                })
        return email_keys_to_values

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        values = dict(custom_values or {})
        if not msg_dict.get('author_id') and msg_dict.get('email_from'):
            author = self._find_or_create_partner(msg_dict['email_from'])
            msg_dict['author_id'] = author.id
        values.setdefault('name', msg_dict.get('subject') or self.env._("No Subject"))
        values.setdefault('email_from', msg_dict.get('email_from'))
        if msg_dict.get('author_id'):
            author = self.env['res.partner'].browse(msg_dict['author_id'])
            if not author.user_ids or author.user_ids[:1].share:
                values.setdefault('partner_id', author.id)
        team = self.env['om.helpdesk.team'].browse(values.get('team_id'))
        if team.company_id:
            values.setdefault('company_id', team.company_id.id)
        ticket = super(OmHelpdeskTicket, self.with_context(mail_create_nolog=True)).message_new(msg_dict, custom_values=values)
        cc_partners = ticket._partner_find_from_emails_single(
            tools.email_split((msg_dict.get('cc') or '')), no_create=True)
        if cc_partners:
            ticket.message_subscribe(cc_partners.ids)
        return ticket

    def message_update(self, msg_dict, update_vals=None):
        for ticket in self:
            partners = ticket._partner_find_from_emails_single(
                tools.email_split(msg_dict.get('cc') or ''), no_create=True)
            if partners:
                ticket.message_subscribe(partners.ids)
        return super().message_update(msg_dict, update_vals=update_vals)

    def _message_post_after_hook(self, message):
        # first answer of the team to the customer
        if not self.date_first_response and message.message_type in ('comment', 'email') \
                and message.subtype_id == self.env.ref('mail.mt_comment') and message.author_id \
                and message.author_id.user_ids and not message.author_id.user_ids[:1].share \
                and message.author_id != self.partner_id:
            self.sudo().date_first_response = message.date or fields.Datetime.now()
        # a customer reply by email reopens a blocked ticket
        if message.message_type == 'email' and self.partner_id and message.author_id == self.partner_id \
                and self.kanban_state == 'blocked':
            self.sudo().kanban_state = 'normal'
        # use the body of the first email as description
        if (
            is_html_empty(self.description)
            and message.subtype_id == self._creation_subtype()
            and message.message_type == 'email'
            and message.body
        ):
            doc = lxml_html.fromstring(message.body)
            for element in doc.xpath('//*[@data-o-mail-quote="1"]'):
                element.getparent().remove(element)
            self.sudo().description = html_sanitize(lxml_html.tostring(doc, encoding='unicode').strip())
        return super()._message_post_after_hook(message)

    def _get_access_action(self, access_uid=None, force_website=False):
        self.ensure_one()
        user = self.env['res.users'].sudo().browse(access_uid) if access_uid else self.env.user
        if not force_website and user and not user.share:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/odoo/action-om_helpdesk.action_helpdesk_ticket/{self.id}',
                'target': 'self',
            }
        return super()._get_access_action(access_uid=access_uid, force_website=force_website)

    def _get_report_base_filename(self):
        self.ensure_one()
        return self.env._('Ticket %s', self.number)

    @api.model
    def _demo_set_dates(self, ticket_ids, ratings):
        """ Give the demo tickets realistic response and closing times, and a few ratings. """
        tickets = self.browse(ticket_ids).exists()
        for index, ticket in enumerate(tickets):
            start = ticket.date_open
            answered = ticket.message_ids.filtered(
                lambda m: m.message_type == 'comment' and m.author_id.user_ids and not m.author_id.user_ids[:1].share)
            values = {}
            if answered:
                values['date_first_response'] = start + timedelta(hours=1 + index % 3)
            closed = start + timedelta(hours=3 + 4 * (index % 4))
            if ticket.is_closed:
                values['date_closed'] = closed
            if values:
                ticket.write(values)
            for line in ticket.sla_status_ids.filtered('reached_datetime'):
                if line.sla_stage_id.is_close:
                    line.reached_datetime = closed
                else:
                    line.reached_datetime = start + timedelta(hours=1 + index % 5)
        for ticket_id, rate in (ratings or {}).items():
            ticket = self.browse(int(ticket_id))
            if ticket.exists() and ticket.partner_id:
                self.env['rating.rating'].create({
                    'res_model_id': self.env['ir.model']._get_id(self._name),
                    'res_id': ticket.id,
                    'partner_id': ticket.partner_id.id,
                    'rated_partner_id': ticket.user_id.partner_id.id,
                    'rating': rate,
                    'consumed': True,
                    'feedback': self.env._('Quick and friendly answer, thank you.') if rate >= 5 else False,
                })

    # ------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------

    def _merge_into(self, target):
        """ Merge `self` into `target`: messages, attachments, followers and descriptions
        are moved, then the merged tickets are archived. """
        sources = self - target
        if not sources:
            return target
        Message = self.env['mail.message'].sudo()
        Attachment = self.env['ir.attachment'].sudo()
        descriptions = []
        for source in sources:
            Message.search([('model', '=', self._name), ('res_id', '=', source.id)]).write({'res_id': target.id})
            Attachment.search([('res_model', '=', self._name), ('res_id', '=', source.id)]).write({'res_id': target.id})
            target.message_subscribe(partner_ids=source.message_partner_ids.ids)
            if not is_html_empty(source.description):
                descriptions.append(Markup('<h4>%s</h4>%s') % (source.display_name, source.description))
        if descriptions:
            target.description = (target.description or Markup()) + Markup('').join(descriptions)
        sources.write({'merged_into_id': target.id, 'active': False})
        target.message_post(
            body=Markup('<p>%s</p><ul>%s</ul>') % (
                self.env._('Merged tickets:'),
                Markup('').join(Markup('<li>%s</li>') % t.display_name for t in sources),
            ),
            subtype_xmlid='mail.mt_note',
        )
        for source in sources:
            source.message_post(
                body=self.env._('This ticket was merged into %s.', target.display_name),
                subtype_xmlid='mail.mt_note',
            )
        return target
