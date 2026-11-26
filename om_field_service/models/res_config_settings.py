from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_notify_on_the_way = fields.Boolean(related='company_id.fs_notify_on_the_way', readonly=False)
    fs_send_report = fields.Boolean(related='company_id.fs_send_report', readonly=False)
    fs_travel_timesheet = fields.Boolean(related='company_id.fs_travel_timesheet', readonly=False)
