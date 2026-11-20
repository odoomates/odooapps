from odoo import fields, models

from ..tools.text_extract import tesseract_available


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_bill_ocr_mode = fields.Selection(related='company_id.om_bill_ocr_mode', readonly=False)
    om_bill_ocr_languages = fields.Char(related='company_id.om_bill_ocr_languages', readonly=False)
    om_bill_ocr_tesseract = fields.Boolean(string="Tesseract Installed", compute='_compute_om_bill_ocr_tesseract')

    def _compute_om_bill_ocr_tesseract(self):
        self.om_bill_ocr_tesseract = tesseract_available()
