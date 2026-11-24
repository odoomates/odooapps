from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

PERIOD_UNITS = [
    ('day', 'Days'),
    ('week', 'Weeks'),
    ('month', 'Months'),
    ('year', 'Years'),
]

# Average number of units in one month, to bring any period to a monthly amount.
UNITS_PER_MONTH = {
    'day': 365.25 / 12,
    'week': 52.1775 / 12,
    'month': 1.0,
    'year': 1.0 / 12,
}


class OmSubscriptionPlan(models.Model):
    _name = 'om.subscription.plan'
    _description = 'Recurring Plan'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company')
    billing_period_value = fields.Integer(string='Bill Every', required=True, default=1)
    billing_period_unit = fields.Selection(PERIOD_UNITS, string='Billing Unit', required=True, default='month')
    billing_period_display = fields.Char(string='Billing Period', compute='_compute_billing_period_display')
    invoice_in_advance = fields.Boolean(
        string='Invoice in Advance', default=True,
        help='Invoice each period at its start. When off, each period is invoiced at its end.')
    invoice_mode = fields.Selection([
        ('posted', 'Post and send'),
        ('draft', 'Leave in draft'),
    ], string='Recurring Invoices', default='posted', required=True,
        help='Post and send: the invoices of the scheduled action are posted, sent by email, paid with the '
             'online payments of the subscription and charged to its saved payment method.\n'
             'Leave in draft: they are created in draft; all of this happens when you post them.')
    duration_value = fields.Integer(
        string='Duration',
        help='Length of the contract term. Leave at 0 for subscriptions that run until they are closed.')
    duration_unit = fields.Selection(PERIOD_UNITS, default='year')
    end_behaviour = fields.Selection([
        ('renew', 'Renew automatically'),
        ('quotation', 'Send a renewal quotation'),
        ('close', 'Close the subscription'),
    ], string='At End of Term', default='renew', required=True)
    renewal_notice_days = fields.Integer(
        string='Renewal Notice (days)', default=15,
        help='Number of days before the end of the term when the renewal quotation is created and sent.')
    auto_close_days = fields.Integer(
        string='Close After Unpaid (days)', default=15,
        help='Close the subscription when an invoice is still unpaid this many days after its due date. '
             '0 keeps the subscription open.')
    payment_retry_count = fields.Integer(
        string='Payment Retries', default=3,
        help='Number of new attempts to charge the saved payment method after a failed payment.')
    payment_retry_interval = fields.Integer(string='Retry Every (days)', default=2)
    user_closable = fields.Boolean(string='Closable by Customer', help='Customers can close it from the portal.')
    user_pausable = fields.Boolean(string='Pausable by Customer', help='Customers can pause and resume it from the portal.')
    pricing_ids = fields.One2many('om.subscription.pricing', 'plan_id', string='Prices')
    subscription_ids = fields.One2many('sale.order', 'subscription_plan_id', string='Subscriptions')
    subscription_count = fields.Integer(compute='_compute_subscription_count')
    note = fields.Html(string='Terms', translate=True)

    _billing_period_positive = models.Constraint(
        'CHECK(billing_period_value > 0)', 'The billing period must be greater than zero.')

    @api.depends('billing_period_value', 'billing_period_unit')
    def _compute_billing_period_display(self):
        labels = dict(self._fields['billing_period_unit']._description_selection(self.env))
        for plan in self:
            if plan.billing_period_value == 1:
                plan.billing_period_display = self.env._('Every %(unit)s', unit=plan._unit_singular())
            else:
                plan.billing_period_display = self.env._(
                    'Every %(count)s %(unit)s', count=plan.billing_period_value,
                    unit=labels.get(plan.billing_period_unit, '').lower())

    def _unit_singular(self):
        self.ensure_one()
        return {
            'day': self.env._('day'),
            'week': self.env._('week'),
            'month': self.env._('month'),
            'year': self.env._('year'),
        }.get(self.billing_period_unit, '')

    def _compute_subscription_count(self):
        data = dict(self.env['sale.order']._read_group(
            [('subscription_plan_id', 'in', self.ids), ('is_subscription', '=', True),
             ('subscription_state', 'in', ('progress', 'paused'))],
            ['subscription_plan_id'], ['__count']))
        for plan in self:
            plan.subscription_count = data.get(plan, 0)

    def _get_billing_delta(self):
        self.ensure_one()
        return relativedelta(**{f'{self.billing_period_unit}s': self.billing_period_value})

    def _get_duration_delta(self):
        self.ensure_one()
        if not self.duration_value:
            return False
        return relativedelta(**{f'{self.duration_unit}s': self.duration_value})

    def _get_monthly_factor(self):
        """Factor to bring the amount of one billing period to a monthly amount."""
        self.ensure_one()
        return UNITS_PER_MONTH[self.billing_period_unit] / (self.billing_period_value or 1)

    def action_open_subscriptions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_sale_subscription.action_subscriptions')
        action['domain'] = [('subscription_plan_id', '=', self.id), ('is_subscription', '=', True)]
        action['context'] = {'default_subscription_plan_id': self.id}
        return action
