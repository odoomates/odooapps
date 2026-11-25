from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    website_subscription_payment_mode = fields.Selection(
        related='website_id.subscription_payment_mode', readonly=False)
    website_subscription_show_recurring_price = fields.Boolean(
        related='website_id.subscription_show_recurring_price', readonly=False)
    website_subscription_invoice_at_payment = fields.Boolean(
        related='website_id.subscription_invoice_at_payment', readonly=False)
