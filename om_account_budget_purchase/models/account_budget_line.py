from odoo import fields, models


class CrossoveredBudgetLines(models.Model):
    _inherit = 'crossovered.budget.lines'

    committed_amount = fields.Monetary(
        string='Committed', compute='_compute_committed_amount',
        help='Amount of the confirmed purchase orders counted by this cost line and not billed yet.')

    def _compute_committed_amount(self):
        for line in self:
            line.committed_amount = line._get_committed_amount()

    def _get_committed_amount(self):
        self.ensure_one()
        # a cost line plans a negative amount
        if self.planned_amount >= 0 or not (self.date_from and self.date_to):
            return 0.0
        order_lines = self.env['purchase.order.line'].search([
            ('company_id', '=', self.company_id.id),
            ('order_id.state', '=', 'purchase'),
            ('display_type', '=', False),
        ])
        items = order_lines._get_budget_items(remaining_only=True)
        return self.currency_id.round(sum(self._get_item_amount(item) for item in items))
