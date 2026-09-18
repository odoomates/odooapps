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

    def test_committed_amount_counts_confirmed_orders_of_the_period(self):
        eur = self.setup_other_currency('EUR')  # 2 EUR for 1 USD
        confirmed = self._order(2)
        confirmed.button_confirm()
        in_euro = self._order(1, price=160.0)
        in_euro.currency_id = eur
        in_euro.button_confirm()
        cancelled = self._order(3)
        cancelled.button_confirm()
        cancelled.button_cancel()
        self._order(4)  # a draft order commits nothing
        next_year = self._order(5)
        next_year.button_confirm()
        next_year.date_approve = '2027-02-01 10:00:00'
        # 200 of the first order and 160 EUR converted to 80 USD, the others do not count
        self.assertEqual(self.budget_line.committed_amount, 280.0)

        # a line limited to other accounts, or a revenue line, commits nothing
        other_account = self.company_data['default_account_revenue']
        position = self.env['account.budget.position'].create({
            'name': 'Revenue accounts', 'account_ids': [Command.set(other_account.ids)],
        })
        budget = self.env['account.budget'].create({'name': 'Budget by position', 'date_from': '2026-01-01',
                                                    'date_to': '2026-12-31'})
        position_line = self.env['account.budget.line'].create({
            'budget_id': budget.id, 'position_id': position.id,
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'planned_amount': 1000.0,
        })
        revenue_line = self.env['account.budget.line'].create({
            'budget_id': budget.id, 'analytic_account_id': self.department.id, 'budget_type': 'revenue',
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'planned_amount': 1000.0,
        })
        self.assertEqual(position_line.committed_amount, 0.0)
        self.assertEqual(revenue_line.committed_amount, 0.0)

    def test_manager_confirms_over_budget_and_refund_commits_again(self):
        self.env.company.budget_block_documents = True
        manager = new_test_user(
            self.env, login='budget_manager',
            groups='purchase.group_purchase_user,account.group_account_user,account.group_account_manager',
            company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        order = self._order(12).with_user(manager)
        self.assertIn('over budget', order.budget_warning)
        # the accounting managers may go over budget, the warning is gone once confirmed
        order.button_confirm()
        self.assertEqual(order.state, 'purchase')
        self.assertFalse(order.budget_warning)
        self.assertEqual(self.budget_line.committed_amount, 1200.0)

        def post(move_type, quantity):
            move = self.env['account.move'].create({
                'move_type': move_type, 'partner_id': self.partner_a.id, 'invoice_date': '2026-03-10',
                'invoice_line_ids': [Command.create({
                    'product_id': self.product.id, 'quantity': quantity, 'price_unit': 100.0, 'tax_ids': [],
                    'purchase_line_id': order.order_line.id,
                    'analytic_distribution': {str(self.department.id): 100},
                })],
            })
            move.action_post()
            self.budget_line.invalidate_recordset(['committed_amount', 'practical_amount'])

        post('in_invoice', 12)
        self.assertEqual(self.budget_line.committed_amount, 0.0)
        self.assertEqual(self.budget_line.practical_amount, 1200.0)
        # the refunded units are to be billed again
        post('in_refund', 2)
        self.assertEqual(self.budget_line.committed_amount, 200.0)
        self.assertEqual(self.budget_line.practical_amount, 1000.0)
