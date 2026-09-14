from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    budget_line_ids = fields.One2many('account.budget.line', 'analytic_account_id', string='Budget Lines')
