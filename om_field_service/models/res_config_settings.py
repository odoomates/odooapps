from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_notify_on_the_way = fields.Boolean(related='company_id.fs_notify_on_the_way', readonly=False)
    fs_send_report = fields.Boolean(related='company_id.fs_send_report', readonly=False)
    fs_travel_timesheet = fields.Boolean(related='company_id.fs_travel_timesheet', readonly=False)
    fs_route_speed = fields.Float(related='company_id.fs_route_speed', readonly=False)
    fs_live_tracking = fields.Boolean(related='company_id.fs_live_tracking', readonly=False)
