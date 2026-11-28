from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fs_notify_on_the_way = fields.Boolean(
        string="Tell the Customer the Technician Is on the Way", default=True)
    fs_send_report = fields.Boolean(string="Email the Job Report When Done", default=True)
    fs_travel_timesheet = fields.Boolean(
        string="Record Travel Time", default=True,
        help="Travel from Start Travel to Start Work is recorded as a timesheet of its own.")
    fs_route_speed = fields.Float(
        string="Average Travel Speed", default=40.0,
        help="Average speed (km/h) between two sites, used to plan the travel time when a route is optimised.")
    fs_live_tracking = fields.Boolean(
        string="Live Tracking Page", default=True,
        help="When the technician leaves for the site, the customer gets a link to a page with the technician, "
             "the status of the visit and the arrival time. The position of the technician is shared from their "
             "phone only while they are on the way, and the page expires once the job is done.")
