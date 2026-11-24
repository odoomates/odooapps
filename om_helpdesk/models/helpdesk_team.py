import ast

from odoo import api, fields, models
from odoo.fields import Domain


class OmHelpdeskTeam(models.Model):
    _name = 'om.helpdesk.team'
    _description = 'Helpdesk Team'
    _inherit = ['mail.alias.mixin', 'rating.parent.mixin', 'mail.thread']
    _order = 'sequence, name'
    _rating_satisfaction_days = 30
    _check_company_auto = True

    def _default_stage_ids(self):
        return self.env['om.helpdesk.stage'].search([('team_ids', '=', False)]) or self.env['om.helpdesk.stage'].search([])

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index')
    description = fields.Html(translate=True, help="Shown to customers, e.g. on the portal.")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string='Team Leader', tracking=True, check_company=True,
        domain="[('share', '=', False)]")
    member_ids = fields.Many2many(
        'res.users', 'om_helpdesk_team_member_rel', 'team_id', 'user_id', string='Members',
        check_company=True, domain="[('share', '=', False)]",
        help="Agents of the team. Automatic assignment picks among them.")
    stage_ids = fields.Many2many(
        'om.helpdesk.stage', 'om_helpdesk_stage_team_rel', 'team_id', 'stage_id', string='Stages',
        default=_default_stage_ids)
    assign_method = fields.Selection([
        ('manual', 'Manual'),
        ('balanced', 'Balanced: fewest open tickets'),
        ('randomly', 'Round robin'),
    ], string='Assignment', required=True, default='manual', tracking=True,
        help="Manual: tickets stay unassigned until someone takes them.\n"
             "Balanced: each new ticket goes to the member with the fewest open tickets.\n"
             "Round robin: members get new tickets in turn.")
    last_assigned_user_id = fields.Many2one('res.users', string='Last Assigned Agent', readonly=True, copy=False)
    resource_calendar_id = fields.Many2one(
        'resource.calendar', string='Working Hours', check_company=True,
        default=lambda self: self.env.company.resource_calendar_id,
        help="Working hours used to compute SLA deadlines in working time.")
    use_sla = fields.Boolean(string='SLA Policies', default=True)
    use_rating = fields.Boolean(
        string='Customer Ratings',
        help="Ask customers to rate the support when their ticket reaches a closing stage.")
    privacy_visibility = fields.Selection([
        ('internal', 'Internal only'),
        ('portal', 'Customers on the portal'),
    ], string='Visibility', required=True, default='portal',
        help="Customers on the portal: customers see and follow their tickets of this team in their portal.")
    sla_ids = fields.One2many('om.helpdesk.sla', 'team_id', string='SLA Policies List')
    ticket_ids = fields.One2many('om.helpdesk.ticket', 'team_id', string='Tickets')

    open_ticket_count = fields.Integer(compute='_compute_ticket_counts', string='Open Tickets')
    unassigned_ticket_count = fields.Integer(compute='_compute_ticket_counts', string='Unassigned Tickets')
    urgent_ticket_count = fields.Integer(compute='_compute_ticket_counts', string='Urgent Tickets')
    sla_failed_ticket_count = fields.Integer(compute='_compute_ticket_counts', string='SLA Failed Tickets')
    my_ticket_count = fields.Integer(compute='_compute_ticket_counts', string='My Tickets')
    closed_today_count = fields.Integer(compute='_compute_ticket_counts', string='Closed Today')
    sla_count = fields.Integer(compute='_compute_sla_count', string='SLA Count')

    @api.depends('ticket_ids.stage_id', 'ticket_ids.user_id', 'ticket_ids.priority')
    def _compute_ticket_counts(self):
        Ticket = self.env['om.helpdesk.ticket']
        base = Domain('team_id', 'in', self.ids) & Domain('is_closed', '=', False)

        def count(domain):
            return dict(Ticket._read_group(base & Domain(domain), ['team_id'], ['__count']))

        open_data = count([])
        unassigned = count([('user_id', '=', False)])
        urgent = count([('priority', '=', '3')])
        failed = count([('sla_fail', '=', True)])
        mine = count([('user_id', '=', self.env.uid)])
        today = fields.Datetime.to_string(fields.Datetime.now().replace(hour=0, minute=0, second=0))
        closed = dict(Ticket._read_group(
            [('team_id', 'in', self.ids), ('is_closed', '=', True), ('date_closed', '>=', today)],
            ['team_id'], ['__count']))
        for team in self:
            team.open_ticket_count = open_data.get(team, 0)
            team.unassigned_ticket_count = unassigned.get(team, 0)
            team.urgent_ticket_count = urgent.get(team, 0)
            team.sla_failed_ticket_count = failed.get(team, 0)
            team.my_ticket_count = mine.get(team, 0)
            team.closed_today_count = closed.get(team, 0)

    def _compute_sla_count(self):
        data = dict(self.env['om.helpdesk.sla']._read_group([('team_id', 'in', self.ids)], ['team_id'], ['__count']))
        for team in self:
            team.sla_count = data.get(team, 0)

    # ------------------------------------------------------------
    # Mail alias
    # ------------------------------------------------------------

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('om.helpdesk.ticket').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or "{}")
            defaults['team_id'] = self.id
        return values

    # ------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------

    def _get_new_ticket_user(self):
        """ Return the agent who gets the next new ticket of this team, or an empty recordset. """
        self.ensure_one()
        members = self.member_ids.filtered(lambda u: u.active and self.company_id in u.company_ids)
        if self.assign_method == 'manual' or not members:
            return self.env['res.users']
        if self.assign_method == 'randomly':
            members = members.sorted('id')
            last = self.last_assigned_user_id
            if last in members:
                index = list(members).index(last)
                user = members[(index + 1) % len(members)]
            else:
                user = members[0]
        else:
            data = dict(self.env['om.helpdesk.ticket'].sudo()._read_group(
                [('team_id', '=', self.id), ('is_closed', '=', False), ('user_id', 'in', members.ids)],
                ['user_id'], ['__count']))
            user = min(members.sorted('id'), key=lambda u: data.get(u, 0))
        self.sudo().last_assigned_user_id = user
        return user

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def _action_tickets(self, domain=None, context=None, name=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_ticket')
        action['display_name'] = name or self.name
        action['domain'] = [('team_id', '=', self.id)] + (domain or [])
        action['context'] = {
            'default_team_id': self.id,
            'search_default_open': 1,
            **(context or {}),
        }
        return action

    def action_view_open_tickets(self):
        return self._action_tickets()

    def action_view_unassigned_tickets(self):
        return self._action_tickets([('user_id', '=', False)], name=self.env._('%s: Unassigned', self.name))

    def action_view_urgent_tickets(self):
        return self._action_tickets([('priority', '=', '3')], name=self.env._('%s: Urgent', self.name))

    def action_view_sla_failed_tickets(self):
        return self._action_tickets([('sla_fail', '=', True)], name=self.env._('%s: SLA Failed', self.name))

    def action_view_my_tickets(self):
        return self._action_tickets([('user_id', '=', self.env.uid)], name=self.env._('%s: My Tickets', self.name))

    def action_view_sla(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_sla')
        action['domain'] = [('team_id', '=', self.id)]
        action['context'] = {'default_team_id': self.id}
        return action

    def action_view_ratings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_rating')
        tickets = self.env['om.helpdesk.ticket'].with_context(active_test=False).search([('team_id', '=', self.id)])
        action['domain'] = [('res_model', '=', 'om.helpdesk.ticket'), ('res_id', 'in', tickets.ids), ('consumed', '=', True)]
        return action

    def action_view_report(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_ticket_report')
        action['context'] = {'search_default_team_id': self.id}
        return action
