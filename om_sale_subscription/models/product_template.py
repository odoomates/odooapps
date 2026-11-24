from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_subscription_product = fields.Boolean(
        string='Subscription',
        help='Sold as a recurring line on subscriptions: invoiced every period of the recurring plan.')
    subscription_pricing_ids = fields.One2many('om.subscription.pricing', 'product_tmpl_id',
                                               string='Recurring Prices', copy=True)
