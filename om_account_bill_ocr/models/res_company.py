from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_bill_ocr_mode = fields.Selection([
        ('auto', "When a Bill Is Uploaded"),
        ('manual', "On Demand"),
        ('off', "Off"),
    ], string="Read the Vendor Bills", default='auto', required=True,
        help="When a Bill Is Uploaded: the bills uploaded or received by email are read at once. "
             "On Demand: with the Read the Bill button of a draft bill.")
    om_bill_ocr_languages = fields.Char(
        string="OCR Languages", default='eng',
        help="The Tesseract languages of the scanned bills, joined by +: eng, eng+fra, eng+ara... "
             "Each one needs its language pack on the server (tesseract-ocr-fra, tesseract-ocr-ara...).")
