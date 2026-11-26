from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fs_notify_on_the_way = fields.Boolean(
        string="Tell the Customer the Technician Is on the Way", default=True)
    fs_send_report = fields.Boolean(string="Email the Job Report When Done", default=True)
    fs_travel_timesheet = fields.Boolean(
        string="Record Travel Time", default=True,
        help="Travel from Start Travel to Start Work is recorded as a timesheet of its own.")
