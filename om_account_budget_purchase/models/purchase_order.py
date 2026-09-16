from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _get_budget_billed_quantity(self):
        """ Quantity of the posted vendor bills, the draft ones are not in the actual amounts yet. """
        self.ensure_one()
        quantity = 0.0
        for bill_line in self.invoice_lines.filtered(lambda line: line.parent_state == 'posted'):
            bill_quantity = bill_line.product_uom_id._compute_quantity(bill_line.quantity, self.uom_id)
            quantity += -bill_quantity if bill_line.move_id.move_type == 'in_refund' else bill_quantity
        return quantity

    def _get_budget_items(self, remaining_only=False):
        """ Expenses of the purchase order lines, see `account.budget.line._get_item_amount`.

        :param remaining_only: count only what is not billed yet
        """
        items = []
        for line in self.filtered(lambda line: not line.display_type and line.product_id and line.product_qty):
            order = line.order_id
            date = fields.Date.to_date(order.date_approve or order.date_order)
            share = 1.0
            if remaining_only:
                share = max(line.product_qty - line._get_budget_billed_quantity(), 0.0) / line.product_qty
                if not share:
                    continue
            accounts = line.product_id.product_tmpl_id.with_company(order.company_id).get_product_accounts(
                fiscal_pos=order.fiscal_position_id)
            amount = order.currency_id._convert(line.price_subtotal * share, order.company_id.currency_id,
                                                order.company_id, date)
            items.append({
                'date': date,
                'account': accounts['expense'],
                'analytic_distribution': line.analytic_distribution,
                'amount': amount,
            })
        return items


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    budget_warning = fields.Html(
        string='Budget Warning', compute='_compute_budget_warning',
        help='Budget lines this purchase order would push over their planned amount once confirmed.')

    @api.depends('state', 'company_id', 'date_order', 'order_line.price_subtotal', 'order_line.product_id',
                 'order_line.analytic_distribution')
    def _compute_budget_warning(self):
        BudgetLine = self.env['account.budget.line']
        for order in self:
            overruns = order._get_budget_overruns() if order.state in ('draft', 'sent', 'to approve') else []
            order.budget_warning = BudgetLine._format_budget_overruns(overruns) if overruns else False

    def _get_budget_overruns(self):
        self.ensure_one()
        if not self.company_id:
            return []
        return self.env['account.budget.line']._get_budget_overruns(
            self.company_id, self.order_line._get_budget_items())

    def button_confirm(self):
        BudgetLine = self.env['account.budget.line']
        for order in self:
            if order.state in ('draft', 'sent') and order.company_id.budget_block_documents \
                    and not self.env.su and not self.env.user.has_group('account.group_account_manager'):
                overruns = order._get_budget_overruns()
                if overruns:
                    raise UserError(_(
                        '%(order)s cannot be confirmed, it goes over budget:\n%(lines)s\nAsk an accounting manager to '
                        'confirm it or to raise the budget.',
                        order=order.display_name, lines=BudgetLine._format_budget_overruns(overruns, html=False)))
        return super().button_confirm()
