from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    planning_mnt_plan_technicians = fields.Boolean(
        string="Plan Technicians", default=True,
        help="The technicians of a scheduled maintenance request are planned with its equipment.")
