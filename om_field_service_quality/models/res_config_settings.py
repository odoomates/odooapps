from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_quality_required = fields.Boolean(related='company_id.fs_quality_required', readonly=False)
