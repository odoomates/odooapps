from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    planning_min_rest_hours = fields.Float(
        string="Minimum Rest", default=0.0,
        help="Minimum hours between the slots of a person on two different days. 0 means no rule.")
    planning_max_hours_day = fields.Float(
        string="Maximum Hours per Day", default=0.0,
        help="Maximum planned hours of a resource on one day. 0 means no rule.")
    planning_max_hours_week = fields.Float(
        string="Maximum Hours per Week", default=0.0,
        help="Maximum planned hours of a resource in one week. 0 means no rule.")
    planning_check_working_time = fields.Boolean(
        string="Warn Outside Working Time", default=True,
        help="Show a conflict when a slot is outside the working schedule of its resource.")
