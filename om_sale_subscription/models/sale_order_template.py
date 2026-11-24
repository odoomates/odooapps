from odoo import fields, models


class SaleOrderTemplate(models.Model):
    _inherit = 'sale.order.template'

    def _default_subscription_plan_id(self):
        if self.env.context.get('subscription_default_plan'):
            return self.env['om.subscription.plan'].search([], limit=1)
        return False

    subscription_plan_id = fields.Many2one(
        'om.subscription.plan', string='Recurring Plan', default=_default_subscription_plan_id,
        help='Quotations made from this template become subscriptions on this plan.')
