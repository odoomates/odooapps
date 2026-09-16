from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetPurchase(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department = cls.env['account.analytic.account'].create({
            'name': 'Workshop', 'plan_id': cls.env['account.analytic.plan'].create({'name': 'Sites'}).id,
        })
        cls.product = cls._create_product(name='Tools', standard_price=100.0, purchase_method='purchase')
        budget = cls.env['account.budget'].create({'name': 'Budget 2026', 'date_from': '2026-01-01',
                                                   'date_to': '2026-12-31'})
        cls.budget_line = cls.env['account.budget.line'].create({
            'budget_id': budget.id, 'analytic_account_id': cls.department.id,
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'planned_amount': 1000.0,
        })
        budget.action_budget_confirm()
        budget.action_budget_validate()

    def _order(self, quantity, price=100.0):
        return self.env['purchase.order'].create({
            'partner_id': self.partner_a.id,
            'date_order': '2026-03-01 10:00:00',
            'order_line': [Command.create({
                'product_id': self.product.id, 'product_qty': quantity, 'price_unit': price, 'tax_ids': [],
                'analytic_distribution': {str(self.department.id): 100},
            })],
        })

    def test_committed_amount_and_warning(self):
        first = self._order(6)
        self.assertFalse(first.budget_warning)
        first.button_confirm()
        self.assertEqual(first.state, 'purchase')
        self.assertEqual(self.budget_line.committed_amount, 600.0)

        second = self._order(5)
        overruns = second._get_budget_overruns()
        self.assertEqual([(overrun['line'], overrun['committed'], overrun['over']) for overrun in overruns],
                         [(self.budget_line, 600.0, 100.0)])
        self.assertIn('over budget', second.budget_warning)

        # billing 4 of the 6 units moves them from committed to actual
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.partner_a.id, 'invoice_date': '2026-03-10',
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id, 'quantity': 4, 'price_unit': 100.0, 'tax_ids': [],
                'purchase_line_id': first.order_line.id,
                'analytic_distribution': {str(self.department.id): 100},
            })],
        })
        self.budget_line.invalidate_recordset(['committed_amount'])
        self.assertEqual(self.budget_line.committed_amount, 600.0, 'a draft bill is not an actual amount yet')
        bill.action_post()
        self.budget_line.invalidate_recordset(['committed_amount', 'practical_amount'])
        self.assertEqual(self.budget_line.committed_amount, 200.0)
        self.assertEqual(self.budget_line.practical_amount, 400.0)

    def test_block_purchase_orders(self):
        self.env.company.budget_block_documents = True
        buyer = new_test_user(self.env, login='budget_buyer',
                              groups='purchase.group_purchase_user,account.group_account_user',
                              company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        order = self._order(12)
        with self.assertRaises(UserError):
            order.with_user(buyer).button_confirm()
        self.assertEqual(order.state, 'draft')
        order.button_confirm()
        self.assertEqual(order.state, 'purchase')

        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_budget.report_budget_vs_actual', self.budget_line.budget_id.ids)[0].decode()
        self.assertIn('Committed', html)
