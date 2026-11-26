from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    planning_time_off_policy = fields.Selection([
        ('keep', 'Keep the slots'),
        ('warn', 'Keep the slots and notify the planners'),
        ('unassign', 'Unassign the employee and notify the planners'),
    ], string="Approved Time Off", default='warn', required=True,
        help="What happens to the planned slots of an employee when a time off overlapping them is "
             "approved. Kept slots show a conflict; unassigned slots become open slots when nobody "
             "else is on them.")
