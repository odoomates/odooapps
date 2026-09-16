from odoo import api, fields, models


class AccountBudgetLine(models.Model):
    _inherit = 'account.budget.line'

    committed_amount = fields.Monetary(
        string='Committed', compute='_compute_committed_amount',
        help='Amount of the confirmed purchase orders counted by this expense line and not billed yet.')

    def _compute_committed_amount(self):
        for line in self:
            line.committed_amount = line._get_committed_amount()

    def _get_committed_amount(self):
        self.ensure_one()
        if self.budget_type != 'expense' or not (self.date_from and self.date_to):
            return 0.0
        order_lines = self.env['purchase.order.line'].search([
            ('company_id', '=', self.company_id.id),
            ('order_id.state', '=', 'purchase'),
            ('display_type', '=', False),
        ])
        items = order_lines._get_budget_items(remaining_only=True)
        return self.currency_id.round(sum(self._get_item_amount(item) for item in items))
