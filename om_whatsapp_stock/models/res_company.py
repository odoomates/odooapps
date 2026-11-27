from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_whatsapp_stock_account_id = fields.Many2one(
        'om.social.account', domain="[('channel', '=', 'whatsapp')]", string="Inventory WhatsApp Account",
        help="Account the delivery messages are sent from automatically. Empty: the account of the template, else the "
             "one of the user.")
