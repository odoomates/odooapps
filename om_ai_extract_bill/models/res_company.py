from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_bill_ocr_engine = fields.Selection([
        ('local', 'On Your Server'),
        ('ai', 'With Your AI Model'),
    ], string='Bill Reading Engine', default='local', required=True,
        help='On Your Server: the text of the PDFs and Tesseract for the scans. '
             'With Your AI Model: the AI model of the AI settings reads the bill (a vision model for scans and photos).')
    om_bill_ai_fallback = fields.Boolean(
        string='Read on the Server When the AI Fails', default=True,
        help='When the AI cannot be reached or a limit is reached, read the bill on your server instead.')
