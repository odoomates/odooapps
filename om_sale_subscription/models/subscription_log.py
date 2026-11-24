from odoo import api, fields, models

EVENT_TYPES = [
    ('new', 'New'),
    ('expansion', 'Expansion'),
    ('contraction', 'Contraction'),
    ('churn', 'Churn'),
    ('transfer', 'Transfer'),
]


class OmSubscriptionLog(models.Model):
    _name = 'om.subscription.log'
    _description = 'Subscription MRR Change'
    _order = 'event_date desc, id desc'
    _rec_name = 'order_id'

    order_id = fields.Many2one('sale.order', string='Subscription', required=True, ondelete='cascade', index=True)
    event_date = fields.Date(string='Date', required=True, default=fields.Date.context_today, index=True)
    event_type = fields.Selection(EVENT_TYPES, string='Type of Change', required=True)
    amount_signed = fields.Monetary(string='MRR Change', currency_field='currency_id')
    recurring_monthly = fields.Monetary(string='MRR After Change', currency_field='currency_id')
    arr_change = fields.Monetary(string='ARR Change', currency_field='currency_id', compute='_compute_arr',
                                 store=True)
    currency_id = fields.Many2one('res.currency', required=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    plan_id = fields.Many2one('om.subscription.plan', string='Recurring Plan')
    user_id = fields.Many2one('res.users', string='Salesperson')
    team_id = fields.Many2one('crm.team', string='Sales Team')
    close_reason_id = fields.Many2one('om.subscription.close.reason')

    @api.depends('amount_signed')
    def _compute_arr(self):
        for log in self:
            log.arr_change = log.amount_signed * 12
