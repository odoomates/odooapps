from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    planning_min_rest_hours = fields.Float(related='company_id.planning_min_rest_hours', readonly=False)
    planning_max_hours_day = fields.Float(related='company_id.planning_max_hours_day', readonly=False)
    planning_max_hours_week = fields.Float(related='company_id.planning_max_hours_week', readonly=False)
    planning_check_working_time = fields.Boolean(
        related='company_id.planning_check_working_time', readonly=False)
