from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountBudgetSplit(models.TransientModel):
    _name = 'account.budget.split'
    _description = 'Split Budget Lines by Period'

    budget_id = fields.Many2one('account.budget', required=True, ondelete='cascade')
    period = fields.Selection([('1', 'Monthly'), ('3', 'Quarterly')], required=True, default='1')
    line_ids = fields.Many2many(
        'account.budget.line', string='Lines to Split',
        domain="[('budget_id', '=', budget_id)]",
        help="Leave empty to split every line of the budget.",
    )

    def action_split(self):
        self.ensure_one()
        if self.budget_id.state != 'draft':
            raise UserError(_('Only the lines of draft budgets can be split.'))
        lines = self.line_ids or self.budget_id.line_ids
        lines._split_by_period(int(self.period))
        return {'type': 'ir.actions.act_window_close'}
