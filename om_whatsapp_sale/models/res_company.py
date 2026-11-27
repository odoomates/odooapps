from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_whatsapp_sale_account_id = fields.Many2one(
        'om.social.account', domain="[('channel', '=', 'whatsapp')]", string="Sales WhatsApp Account",
        help="Account the order confirmations are sent from automatically. Empty: the account of the template, else "
             "the one of the user.")
    om_whatsapp_quotation_template_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp Quotation Template", domain="[('model', '=', 'sale.order')]",
        help="Offered by the Send by WhatsApp button of a quotation.")
    om_whatsapp_order_template_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp Order Template", domain="[('model', '=', 'sale.order')]",
        help="Offered by the Send by WhatsApp button of a sales order, and sent on confirmation when that is set.")
    om_whatsapp_order_auto = fields.Boolean(
        "Send Order Confirmations by WhatsApp",
        help="Each order goes to the customer by WhatsApp once, when it is confirmed: by a salesperson, a signature, "
             "or an online payment.")
