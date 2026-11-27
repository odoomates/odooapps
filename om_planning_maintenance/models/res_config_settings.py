from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    planning_mnt_plan_technicians = fields.Boolean(
        related='company_id.planning_mnt_plan_technicians', readonly=False)
