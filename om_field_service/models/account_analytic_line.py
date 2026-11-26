from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    fs_time_type = fields.Selection([
        ('travel', 'Travel'),
        ('work', 'Work'),
    ], string="Field Service Time", help="Travel or work time recorded on a field service job.")
