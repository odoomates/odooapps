from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_whatsapp_invoice_account_id = fields.Many2one(
        'om.social.account', domain="[('channel', '=', 'whatsapp')]", string="Invoicing WhatsApp Account",
        help="Account the invoices and receipts are sent from automatically. Empty: the account of the template, "
             "else the one of the user.")
    om_whatsapp_invoice_template_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp Invoice Template", domain="[('model', '=', 'account.move')]",
        help="Sent with the invoices: by the Send by WhatsApp button, and on posting when that is set.")
    om_whatsapp_refund_template_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp Credit Note Template", domain="[('model', '=', 'account.move')]",
        help="Sent with the credit notes: by the Send by WhatsApp button, and on posting when that is set.")
    om_whatsapp_invoice_auto = fields.Boolean(
        "Send Invoices by WhatsApp on Posting",
        help="Each customer invoice and credit note goes to the customer by WhatsApp once, when it is posted.")
    om_whatsapp_payment_template_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp Payment Receipt Template",
        domain="[('model', '=', 'account.payment')]",
        help="Sent with the customer payments: by the Send by WhatsApp button, and on confirmation when that is set.")
    om_whatsapp_payment_auto = fields.Boolean(
        "Send Payment Receipts by WhatsApp",
        help="Each customer payment sends its receipt to the customer by WhatsApp once, when it is confirmed.")
