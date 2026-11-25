from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    subscription_payment_mode = fields.Selection([
        ('token', 'Hide providers that cannot save it'),
        ('any', 'Allow them, invoices are sent by email'),
    ], string='Subscriptions without Saved Payment', default='token', required=True,
        help='Subscriptions bought online pay their next invoices with the payment method saved at checkout.')
    subscription_invoice_at_payment = fields.Boolean(
        string='Invoice Subscriptions at Payment', default=True,
        help='Create, pay and send the invoice of the first period as soon as a subscription is paid online. '
             'Otherwise the daily subscription job creates it.')
    subscription_show_recurring_price = fields.Boolean(
        string='Show Recurring Prices',
        help='Show the recurring price instead of the sales price on the shop for subscription products.')
