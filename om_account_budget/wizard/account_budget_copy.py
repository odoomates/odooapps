from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountBudgetCopy(models.TransientModel):
    _name = 'account.budget.copy'
    _description = 'Copy a Budget to Another Period'

    budget_id = fields.Many2one('account.budget', required=True, ondelete='cascade')
    name = fields.Char('New Budget Name', required=True, compute='_compute_period', store=True, readonly=False,
                       precompute=True)
    date_from = fields.Date('Start Date', required=True, compute='_compute_period', store=True, readonly=False,
                            precompute=True)
    date_to = fields.Date('End Date', required=True, compute='_compute_period', store=True, readonly=False,
                          precompute=True)

    @api.depends('budget_id')
    def _compute_period(self):
        for wizard in self:
            budget = wizard.budget_id
            if not budget:
                continue
            # the period right after the one of the budget, with the same length
            wizard.date_from = budget.date_to + relativedelta(days=1)
            if budget.date_from.day == 1:
                length = relativedelta(budget.date_to + relativedelta(days=1), budget.date_from)
                wizard.date_to = wizard.date_from + length - relativedelta(days=1)
            else:
                wizard.date_to = wizard.date_from + (budget.date_to - budget.date_from)
            wizard.name = _('%s (copy)', budget.name)

    def action_copy(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('The new budget must start before it ends.'))
        new_budget = self.budget_id.copy_to_period(self.date_from, self.date_to, self.name)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.budget',
            'view_mode': 'form',
            'res_id': new_budget.id,
        }
