from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_bill_ocr_engine = fields.Selection(related='company_id.om_bill_ocr_engine', readonly=False)
    om_bill_ai_fallback = fields.Boolean(related='company_id.om_bill_ai_fallback', readonly=False)
