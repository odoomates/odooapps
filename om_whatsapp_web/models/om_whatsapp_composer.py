from odoo import fields, models


class OmWhatsappComposer(models.TransientModel):
    _inherit = 'om.whatsapp.composer'

    account_provider = fields.Selection(related='account_id.provider')
