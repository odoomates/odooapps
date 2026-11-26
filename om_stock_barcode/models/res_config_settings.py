from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_barcode_sound = fields.Boolean(related='company_id.om_barcode_sound', readonly=False)
    om_barcode_camera = fields.Boolean(related='company_id.om_barcode_camera', readonly=False)
