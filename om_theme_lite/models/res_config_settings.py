from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_home_background = fields.Image(related='company_id.om_home_background', readonly=False)
    om_favicon = fields.Image(
        related='company_id.om_favicon', readonly=False, string='Backend Favicon')
