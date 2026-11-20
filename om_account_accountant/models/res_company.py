from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    credit_limit_block = fields.Boolean(
        string='Block Over the Credit Limit',
        help="Refuse to post a customer invoice that brings the customer over its credit limit. The users "
             "allowed to override the credit limit can still post it, and the override is logged on the invoice.")
    om_invoice_signature = fields.Boolean(
        string='Signature on Invoices',
        help='Print the name and the signature of the signing user at the bottom of the customer invoices.')
    om_invoice_signer_id = fields.Many2one(
        'res.users', string='Signing User',
        help='Who signs the invoices; leave empty for the salesperson of each invoice.')
