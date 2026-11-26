from odoo import api, fields, models


class OmQualityAction(models.Model):
    _name = 'om.quality.action'
    _description = 'Corrective or Preventive Action'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state, date_deadline, id'
    _check_company_auto = True

    name = fields.Char(string='Action', required=True, tracking=True)
    alert_id = fields.Many2one('om.quality.alert', string='Non-conformance', required=True, index=True,
                               ondelete='cascade', check_company=True)
    company_id = fields.Many2one(related='alert_id.company_id', string='Company', store=True, index=True)
    team_id = fields.Many2one(related='alert_id.team_id', string='Team', store=True)
    product_id = fields.Many2one(related='alert_id.product_id', string='Product', store=True)
    action_type = fields.Selection([
        ('containment', 'Containment'),
        ('corrective', 'Corrective'),
        ('preventive', 'Preventive'),
    ], string='Type', required=True, default='corrective', tracking=True,
        help="Containment: stop the problem now. Corrective: remove its cause. "
             "Preventive: keep it from happening elsewhere.")
    user_id = fields.Many2one('res.users', string='Owner', required=True, tracking=True, check_company=True,
                              domain="[('share', '=', False)]", default=lambda self: self.env.user)
    description = fields.Html()
    date_deadline = fields.Date(string='Due Date', tracking=True, index=True)
    date_done = fields.Date(string='Done On', readonly=True, copy=False, tracking=True)
    state = fields.Selection([
        ('open', 'Open'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', required=True, default='open', tracking=True, copy=False, index=True)
    effectiveness = fields.Selection([
        ('pending', 'To Verify'),
        ('effective', 'Effective'),
        ('not_effective', 'Not Effective'),
    ], string='Effectiveness', default='pending', required=True, tracking=True, copy=False,
        help="Verified after the action is done: did it remove the problem?")
    effectiveness_note = fields.Text(string='Verification Notes')
    is_late = fields.Boolean(compute='_compute_is_late', string='Late')

    @api.depends('date_deadline', 'state')
    def _compute_is_late(self):
        today = fields.Date.context_today(self)
        for action in self:
            action.is_late = action.state == 'open' and bool(action.date_deadline) and action.date_deadline < today

    @api.model_create_multi
    def create(self, vals_list):
        actions = super().create(vals_list)
        for action in actions:
            action._schedule_owner_activity()
        return actions

    def write(self, vals):
        res = super().write(vals)
        if vals.get('user_id') or vals.get('date_deadline'):
            for action in self.filtered(lambda a: a.state == 'open'):
                action.activity_unlink(['mail.mail_activity_data_todo'])
                action._schedule_owner_activity()
        return res

    def _schedule_owner_activity(self):
        self.ensure_one()
        if self.user_id and self.state == 'open':
            self.activity_schedule(
                'mail.mail_activity_data_todo', date_deadline=self.date_deadline or fields.Date.context_today(self),
                summary=self.name, user_id=self.user_id.id)

    def action_done(self):
        self.write({'state': 'done', 'date_done': fields.Date.context_today(self)})
        self.activity_feedback(['mail.mail_activity_data_todo'])
        for action in self:
            action.alert_id.message_post(body=self.env._("Action done: %s", action.name))
        return True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        self.activity_unlink(['mail.mail_activity_data_todo'])
        return True

    def action_reopen(self):
        self.write({'state': 'open', 'date_done': False})
        for action in self:
            action._schedule_owner_activity()
        return True

    def action_set_effective(self):
        self.write({'effectiveness': 'effective'})
        return True

    def action_set_not_effective(self):
        self.write({'effectiveness': 'not_effective'})
        return True
