from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    om_whatsapp_receipt = fields.Boolean(
        'WhatsApp Receipts', help="The send receipt dialog of the POS gets a WhatsApp number and button.")
    om_whatsapp_receipt_template_id = fields.Many2one(
        'om.whatsapp.template', string='WhatsApp Receipt Template', domain="[('model', '=', 'pos.order')]",
        help="The text of the receipt sent by WhatsApp. Empty: Point of Sale: Receipt.")
    om_whatsapp_account_id = fields.Many2one(
        'om.social.account', domain="[('channel', '=', 'whatsapp')]", string='POS WhatsApp Account',
        help="The account the receipts are sent from. Empty: the account of the template, else the one of the "
             "cashier.")
