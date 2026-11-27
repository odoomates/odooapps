from odoo import fields, models

DEFAULT_MESSAGE = "Good news! Your order {order} is on its way with {carrier}.\n{tracking}"


class OmWhatsappAccount(models.Model):
    _inherit = 'om.whatsapp.account'

    om_ai_shipping_messages = fields.Boolean(
        'Shipping Messages', default=True,
        help="When a delivery of an order taken on WhatsApp is validated, the customer gets the carrier and the "
             "tracking link in the conversation.")
    om_ai_shipping_text = fields.Text(
        'Shipping Message', translate=True, default=DEFAULT_MESSAGE,
        help="{order}, {delivery}, {carrier} and {tracking} (the tracking link, else the tracking reference) are "
             "replaced. A line left empty by them is dropped.")
