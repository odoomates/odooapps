from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

BUDGET_TYPES = [('expense', 'Expense'), ('revenue', 'Revenue')]


class AccountBudgetPosition(models.Model):
    _name = 'account.budget.position'
    _description = 'Budgetary Position'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    budget_type = fields.Selection(
        BUDGET_TYPES, string='Type', required=True, default='expense',
        help="Expense: the planned amounts are costs, spending more than planned is over budget.\n"
             "Revenue: the planned amounts are incomes, earning more than planned is above budget.",
    )
    account_ids = fields.Many2many(
        'account.account', 'account_budget_position_account_rel', 'position_id', 'account_id',
        string='Accounts', check_company=True,
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)

    @api.constrains('account_ids')
    def _check_account_ids(self):
        for position in self:
            if not position.account_ids:
                raise ValidationError(_('The budgetary position "%s" must have at least one account.', position.name))
