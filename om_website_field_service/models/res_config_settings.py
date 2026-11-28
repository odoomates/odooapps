from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_request_review = fields.Boolean(related='company_id.fs_request_review', readonly=False)
    fs_request_project_id = fields.Many2one(related='company_id.fs_request_project_id', readonly=False)
