from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    planning_time_off_policy = fields.Selection(related='company_id.planning_time_off_policy', readonly=False)
