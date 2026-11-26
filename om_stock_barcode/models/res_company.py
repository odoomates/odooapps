from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_barcode_sound = fields.Boolean(
        string="Barcode Sounds", default=True,
        help="Play a sound and vibrate on each scan in the Barcode app.")
    om_barcode_camera = fields.Boolean(
        string="Barcode Camera", default=True,
        help="Show the camera button in the Barcode app, to scan with the camera of a phone or tablet.")
