from odoo import api, fields, models
from odoo.fields import Domain

ALERT_PRIORITY = [
    ('0', 'Low'),
    ('1', 'Medium'),
    ('2', 'High'),
    ('3', 'Urgent'),
]


class OmQualityAlert(models.Model):
    _name = 'om.quality.alert'
    _description = 'Non-conformance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, id desc'
    _check_company_auto = True
    _rec_names_search = ['name', 'number']

    def _default_team_id(self):
        team_id = self.env.context.get('default_team_id')
        if team_id:
            return self.env['om.quality.team'].browse(team_id)
        return self.env['om.quality.team'].search(
            [('member_ids', 'in', self.env.uid), ('company_id', 'in', self.env.companies.ids)], limit=1
        ) or self.env['om.quality.team'].search([('company_id', 'in', self.env.companies.ids)], limit=1)

    number = fields.Char(string='Number', readonly=True, copy=False, default='/', index='trigram')
    name = fields.Char(string='Title', required=True, tracking=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency')
    team_id = fields.Many2one(
        'om.quality.team', string='Team', index=True, tracking=True, check_company=True, default=_default_team_id)
    user_id = fields.Many2one(
        'res.users', string='Responsible', index=True, tracking=True, check_company=True,
        domain="[('share', '=', False)]", default=lambda self: self.env.user)
    stage_id = fields.Many2one(
        'om.quality.alert.stage', string='Stage', index=True, tracking=True, copy=False, ondelete='restrict',
        compute='_compute_stage_id', store=True, readonly=False, group_expand='_read_group_stage_ids',
        domain="['|', ('team_ids', '=', False), ('team_ids', 'in', team_id)]")
    is_closed = fields.Boolean(related='stage_id.is_closed', store=True, string='Closed', index=True)
    priority = fields.Selection(ALERT_PRIORITY, default='0', index=True, tracking=True)
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked'),
    ], string='Status', default='normal', required=True, copy=False, tracking=True)
    color = fields.Integer(string='Color Index')
    tag_ids = fields.Many2many('om.quality.tag', string='Tags')
    product_id = fields.Many2one('product.product', string='Product', index=True, tracking=True, check_company=True)
    product_categ_id = fields.Many2one(related='product_id.categ_id', string='Product Category', store=True)
    partner_id = fields.Many2one('res.partner', string='Partner', index=True, tracking=True, check_company=True,
                                 help="The vendor or customer concerned.")
    reason_id = fields.Many2one('om.quality.reason', string='Failure Reason', tracking=True)
    root_cause = fields.Html(string='Root Cause')
    cost = fields.Monetary(string='Cost of Non-quality', currency_field='currency_id', tracking=True,
                           help="Scrap, rework, returns and time spent.")
    check_ids = fields.Many2many(
        'om.quality.check', 'om_quality_alert_check_rel', 'alert_id', 'check_id', string='Checks', copy=False)
    check_count = fields.Integer(compute='_compute_counts', string='Checks Count')
    action_ids = fields.One2many('om.quality.action', 'alert_id', string='Actions')
    action_count = fields.Integer(compute='_compute_counts', string='Actions Count')
    action_open_count = fields.Integer(compute='_compute_counts', string='Open Actions')
    res_model = fields.Char(string='Document Model', index=True)
    res_id = fields.Many2oneReference(string='Document ID', model_field='res_model', index=True)
    document_name = fields.Char(string='Document', compute='_compute_document_name', store=True)
    date_open = fields.Datetime(string='Opened On', default=fields.Datetime.now, readonly=True, copy=False, index=True)
    date_closed = fields.Datetime(string='Closed On', compute='_compute_date_closed', store=True, copy=False, index=True)
    days_open = fields.Float(string='Days Open', compute='_compute_days_open', aggregator='avg')

    @api.depends('check_ids', 'action_ids.state')
    def _compute_counts(self):
        for alert in self:
            alert.check_count = len(alert.check_ids)
            alert.action_count = len(alert.action_ids)
            alert.action_open_count = len(alert.action_ids.filtered(lambda action: action.state == 'open'))

    @api.depends('res_model', 'res_id')
    def _compute_document_name(self):
        for alert in self:
            document = alert._get_document()
            alert.document_name = document.sudo().display_name if document else False

    @api.depends('team_id')
    def _compute_stage_id(self):
        for alert in self:
            if alert.stage_id and (not alert.team_id or not alert.stage_id.team_ids or alert.team_id in alert.stage_id.team_ids):
                continue
            alert.stage_id = alert._stage_find(alert.team_id.id)

    @api.depends('is_closed')
    def _compute_date_closed(self):
        for alert in self:
            if alert.is_closed:
                alert.date_closed = alert.date_closed or fields.Datetime.now()
            else:
                alert.date_closed = False

    def _compute_days_open(self):
        now = fields.Datetime.now()
        for alert in self:
            end = alert.date_closed or now
            alert.days_open = (end - alert.date_open).total_seconds() / 86400 if alert.date_open else 0.0

    def _get_document(self):
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            return self.env[self.res_model].browse(self.res_id).exists()
        return None

    def _stage_find(self, team_id):
        domain = Domain('team_ids', '=', False)
        if team_id:
            domain |= Domain('team_ids', 'in', [team_id])
        return self.env['om.quality.alert.stage'].search(domain, order='sequence, id', limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        team_id = self.env.context.get('default_team_id')
        search_domain = Domain('team_ids', '=', False)
        if team_id:
            search_domain |= Domain('team_ids', 'in', [team_id])
        return stages.search(Domain('id', 'in', stages.ids) | search_domain, order=stages._order)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('number') or vals['number'] == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['number'] = self.env['ir.sequence'].with_company(company).next_by_code('om.quality.alert') or '/'
        alerts = super().create(vals_list)
        for alert in alerts.filtered('user_id'):
            alert.message_subscribe(partner_ids=alert.user_id.partner_id.ids)
        return alerts

    def write(self, vals):
        if 'stage_id' in vals and 'kanban_state' not in vals:
            vals['kanban_state'] = 'normal'
        res = super().write(vals)
        if vals.get('user_id'):
            for alert in self:
                alert.message_subscribe(partner_ids=alert.user_id.partner_id.ids)
        return res

    def _compute_display_name(self):
        for alert in self:
            alert.display_name = f'{alert.number} {alert.name}' if alert.number and alert.number != '/' else alert.name

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        values = dict(custom_values or {})
        values.setdefault('name', msg_dict.get('subject') or self.env._('No Subject'))
        values.setdefault('description', msg_dict.get('body'))
        partner_ids = [pid for pid in self._mail_find_partner_from_emails([msg_dict.get('email_from')]) if pid]
        if partner_ids and 'partner_id' not in values:
            values['partner_id'] = partner_ids[0].id
        return super().message_new(msg_dict, custom_values=values)

    def action_view_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_quality.action_om_quality_check')
        action['domain'] = [('id', 'in', self.check_ids.ids)]
        action['context'] = {}
        return action

    def action_view_actions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_quality.action_om_quality_action')
        action['domain'] = [('alert_id', '=', self.id)]
        action['context'] = {'default_alert_id': self.id}
        return action

    def action_open_document(self):
        self.ensure_one()
        document = self._get_document()
        if not document:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': document._name,
            'res_id': document.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
