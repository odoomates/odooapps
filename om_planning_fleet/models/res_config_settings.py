from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    planning_fleet_follow_driver = fields.Boolean(
        related='company_id.planning_fleet_follow_driver', readonly=False)
