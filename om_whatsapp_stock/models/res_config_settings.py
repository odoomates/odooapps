from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_whatsapp_stock_account_id = fields.Many2one(related='company_id.om_whatsapp_stock_account_id', readonly=False)
