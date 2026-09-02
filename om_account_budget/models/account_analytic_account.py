from odoo import fields, models, api


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    crossovered_budget_line = fields.One2many(
        'crossovered.budget.lines', 'analytic_account_id', 'Budget Lines'
    )
