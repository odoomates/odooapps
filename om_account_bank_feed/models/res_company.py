from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    bank_feed_reminder_days = fields.Integer(
        string='Consent Reminder (Days)', default=7,
        help="Remind the responsible of a bank feed this number of days before its consent expires.")
