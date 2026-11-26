from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_quality_alert_on_failure = fields.Boolean(
        string='Raise Non-conformance on Failure', default=True,
        help="Default of new control points: a failed check raises a non-conformance.")
