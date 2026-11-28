from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fs_quality_required = fields.Boolean(
        string="Quality Checks Required", default=True,
        help="A field service job cannot be marked as done while one of its quality checks is still to do. "
             "Blocking control points hold the job until their check passes, whatever this setting.")
