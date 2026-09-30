from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    retained_earnings_account_id = fields.Many2one(
        'account.account', string='Retained Earnings Account', check_company=True,
        domain=[('account_type', '=', 'equity')],
        help='Account receiving the earnings of the fiscal years when they are closed.')
