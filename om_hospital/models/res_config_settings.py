from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hospital_cancel_days = fields.Integer(
        string='Cancellation Limit', config_parameter='om_hospital.cancel_days',
        help="Appointments can be cancelled up to this many days before their date. 0: any time.")
