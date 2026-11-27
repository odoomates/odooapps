from odoo import api, fields, models


class Website(models.Model):
    _inherit = 'website'

    om_whatsapp_order_template_id = fields.Many2one(
        'om.whatsapp.template', string='WhatsApp Order Confirmation', domain="[('model', '=', 'sale.order')]",
        help="Sent once to the customer when an order of this website is confirmed. Empty: the order confirmation "
             "of Sales, when it is sent automatically.")
    om_whatsapp_cart_template_id = fields.Many2one(
        'om.whatsapp.template', string='WhatsApp Cart Reminder', domain="[('model', '=', 'sale.order')]",
        help="Sent once to a signed-in customer who left their cart, after the delay of the abandoned carts. Empty: "
             "no WhatsApp reminder.")
    om_whatsapp_cart_since = fields.Datetime(
        'WhatsApp Cart Reminders Since', compute='_compute_om_whatsapp_cart_since', store=True, readonly=True,
        help="Only the carts left after the reminders were turned on get one: the old ones are left alone.")

    @api.depends('om_whatsapp_cart_template_id', 'send_abandoned_cart_followup')
    def _compute_om_whatsapp_cart_since(self):
        for website in self:
            if not website.om_whatsapp_cart_template_id or not website.send_abandoned_cart_followup:
                website.om_whatsapp_cart_since = False
            elif not website.om_whatsapp_cart_since:
                website.om_whatsapp_cart_since = fields.Datetime.now()
