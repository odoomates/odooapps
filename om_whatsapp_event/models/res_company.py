from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_whatsapp_event_account_id = fields.Many2one(
        'om.social.account', domain="[('channel', '=', 'whatsapp')]", string="Events WhatsApp Account",
        help="Account the WhatsApp messages of the event communication are sent from. Empty: the account of the "
             "template, else the one of the user.")
