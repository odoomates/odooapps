from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudget(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.expense_account = cls.company_data['default_account_expense']
        cls.revenue_account = cls.company_data['default_account_revenue']
        Plan = cls.env['account.analytic.plan']
        # a plan other than the project plan stores its accounts in its own column of the analytic items
        cls.plan = next(
            plan for plan in (Plan.create({'name': 'Departments'}), Plan.create({'name': 'Regions'}))
            if plan._column_name() != 'account_id'
        )
        cls.analytic_accounts = cls.env['account.analytic.account'].create([
            {'name': f'Department {index}', 'plan_id': cls.plan.id} for index in range(3)
        ])
        cls.position = cls.env['account.budget.position'].create({
            'name': 'Expenses',
            'account_ids': [Command.set(cls.expense_account.ids)],
        })
        cls.revenue_position = cls.env['account.budget.position'].create({
            'name': 'Revenues',
            'budget_type': 'revenue',
            'account_ids': [Command.set(cls.revenue_account.ids)],
        })
        cls.budget = cls.env['account.budget'].create({
            'name': 'Budget 2026',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })

    def _create_move(self, move_type, amount, account, analytic_account=None, post=True, move_date='2026-01-05'):
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner_a.id,
            'invoice_date': move_date,
            'date': move_date,
            'invoice_line_ids': [Command.create({
                'name': 'Line',
                'price_unit': amount,
                'account_id': account.id,
                'tax_ids': [],
                'analytic_distribution': {str(analytic_account.id): 100} if analytic_account else False,
            })],
        })
        if post:
            move.action_post()
        return move

    def _create_bill(self, amount, analytic_account=None, post=True, move_date='2026-01-05'):
        return self._create_move('in_invoice', amount, self.expense_account, analytic_account, post, move_date)

    def _create_line(self, budget=None, **vals):
        return self.env['account.budget.line'].create({
            'budget_id': (budget or self.budget).id,
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'planned_amount': 1000.0,
            **vals,
        })

    # -------------------------------------------------------------------------
    # Amounts
    # -------------------------------------------------------------------------

    def test_practical_amount_analytic_account_of_other_plan(self):
        self._create_bill(100.0, analytic_account=self.analytic_accounts[0])
        line = self._create_line(analytic_account_id=self.analytic_accounts[0].id, position_id=self.position.id)
        self.assertEqual(line.budget_type, 'expense')
        self.assertEqual(line.practical_amount, 100.0)

    def test_practical_amount_only_posted_entries(self):
        self._create_bill(100.0)
        self._create_bill(50.0, post=False)
        line = self._create_line(position_id=self.position.id)
        self.assertEqual(line.practical_amount, 100.0)

    def test_revenue_line(self):
        self._create_move('out_invoice', 400.0, self.revenue_account)
        line = self._create_line(position_id=self.revenue_position.id)
        self.assertEqual(line.budget_type, 'revenue')
        self.assertEqual(line.practical_amount, 400.0)
        with freeze_time('2026-01-01'):
            line.invalidate_recordset(['theoretical_amount', 'is_over_budget', 'is_above_budget'])
            self.assertTrue(line.is_above_budget)
            self.assertFalse(line.is_over_budget)

    def test_practical_amount_batched(self):
        for account, amount in zip(self.analytic_accounts, (10.0, 20.0, 30.0)):
            self._create_bill(amount, analytic_account=account)
        lines = self.env['account.budget.line'].browse([
            self._create_line(analytic_account_id=account.id, position_id=self.position.id).id
            for account in self.analytic_accounts
        ])
        lines.invalidate_recordset(['practical_amount'])

        AnalyticLine = self.registry['account.analytic.line']
        with patch.object(AnalyticLine, '_read_group', autospec=True,
                          side_effect=AnalyticLine._read_group) as read_group:
            self.assertEqual(lines.mapped('practical_amount'), [10.0, 20.0, 30.0])
        self.assertEqual(read_group.call_count, 1)

    def test_theoretical_amount_includes_the_last_day(self):
        line = self._create_line(position_id=self.position.id, date_from='2026-01-01', date_to='2026-01-10')
        for today, expected in (('2025-12-31', 0.0), ('2026-01-01', 100.0), ('2026-01-10', 1000.0),
                                ('2026-02-01', 1000.0)):
            with freeze_time(today):
                line.invalidate_recordset(['theoretical_amount'])
                self.assertEqual(line.theoretical_amount, expected, today)

    def test_theoretical_amount_at_a_date(self):
        line = self._create_line(position_id=self.position.id, distribution='at_date', planned_date='2026-06-15')
        for today, expected in (('2026-06-14', 0.0), ('2026-06-15', 1000.0)):
            with freeze_time(today):
                line.invalidate_recordset(['theoretical_amount'])
                self.assertEqual(line.theoretical_amount, expected, today)
        with self.assertRaises(ValidationError):
            line.planned_date = '2027-01-15'

    def test_grouped_achievement_is_a_ratio(self):
        self._create_bill(250.0)
        self._create_line(position_id=self.position.id)
        with freeze_time('2027-01-01'):
            [group] = self.env['account.budget.line'].formatted_read_group(
                [('budget_id', '=', self.budget.id)],
                groupby=['budget_id'],
                aggregates=['practical_amount:sum', 'theoretical_amount:sum', 'achievement:sum'],
            )
        self.assertEqual(group['practical_amount:sum'], 250.0)
        self.assertEqual(group['theoretical_amount:sum'], 1000.0)
        self.assertEqual(group['achievement:sum'], 0.25)

    def test_budget_totals(self):
        self._create_bill(300.0)
        self._create_move('out_invoice', 500.0, self.revenue_account)
        self._create_line(position_id=self.position.id)
        self._create_line(position_id=self.revenue_position.id, planned_amount=2000.0)
        with freeze_time('2027-01-01'):
            self.budget.invalidate_recordset()
            self.assertEqual(self.budget.expense_planned_amount, 1000.0)
            self.assertEqual(self.budget.expense_practical_amount, 300.0)
            self.assertEqual(self.budget.expense_achievement, 0.3)
            self.assertEqual(self.budget.revenue_planned_amount, 2000.0)
            self.assertEqual(self.budget.revenue_practical_amount, 500.0)

    def test_over_budget_search(self):
        self._create_bill(900.0)
        line = self._create_line(position_id=self.position.id)
        with freeze_time('2026-01-31'):
            self.assertTrue(line.is_over_budget)
            self.assertIn(line, self.env['account.budget.line'].search([('is_over_budget', '=', True)]))
            self.assertIn(self.budget, self.env['account.budget'].search([('is_over_budget', '=', True)]))

    # -------------------------------------------------------------------------
    # Constraints and lock
    # -------------------------------------------------------------------------

    def test_lines_need_position_or_analytic_account(self):
        with self.assertRaises(ValidationError):
            self.env['account.budget.line'].create([
                {'budget_id': self.budget.id, 'date_from': '2026-01-01', 'date_to': '2026-12-31',
                 'planned_amount': 1.0, 'position_id': self.position.id},
                {'budget_id': self.budget.id, 'date_from': '2026-01-01', 'date_to': '2026-12-31',
                 'planned_amount': 1.0},
            ])

    def test_dates_constraints(self):
        with self.assertRaises(ValidationError):
            self.env['account.budget'].create({'name': 'Wrong', 'date_from': '2026-12-31', 'date_to': '2026-01-01'})
        with self.assertRaises(ValidationError):
            self._create_line(position_id=self.position.id, date_from='2026-03-01', date_to='2026-02-01')
        with self.assertRaises(ValidationError):
            self._create_line(position_id=self.position.id, date_from='2025-12-01')

    def test_overlapping_lines(self):
        self._create_line(position_id=self.position.id, date_from='2026-01-01', date_to='2026-06-30')
        self._create_line(position_id=self.position.id, date_from='2026-07-01', date_to='2026-12-31')
        self._create_line(position_id=self.position.id, analytic_account_id=self.analytic_accounts[0].id)
        with self.assertRaises(ValidationError):
            self._create_line(position_id=self.position.id, date_from='2026-06-01', date_to='2026-07-31')

    def test_negative_planned_amount(self):
        with self.assertRaises(ValidationError):
            self._create_line(position_id=self.position.id, planned_amount=-10.0)

    def test_company_consistency(self):
        other_company = self.setup_other_company()['company']
        other_position = self.env['account.budget.position'].with_company(other_company).create({
            'name': 'Other',
            'company_id': other_company.id,
            'account_ids': [Command.set(self.env['account.account'].with_company(other_company).search(
                [('company_ids', 'in', other_company.id), ('account_type', '=', 'expense')], limit=1).ids)],
        })
        with self.assertRaises(UserError):
            self._create_line(position_id=other_position.id)

    def test_locked_budget(self):
        line = self._create_line(position_id=self.position.id)
        self.budget.action_budget_confirm()
        with self.assertRaises(UserError):
            line.planned_amount = 10.0
        with self.assertRaises(UserError):
            self._create_line(position_id=self.revenue_position.id)
        with self.assertRaises(UserError):
            self.budget.date_to = '2026-11-30'
        self.budget.user_id = self.env.user
        self.budget.action_budget_draft()
        line.planned_amount = 10.0

    def test_only_managers_approve(self):
        accountant = new_test_user(self.env, login='budget_accountant', groups='account.group_account_user')
        budget = self.budget.with_user(accountant)
        budget.action_budget_confirm()
        with self.assertRaises(AccessError):
            budget.action_budget_validate()
        self.budget.action_budget_validate()
        self.assertEqual(self.budget.state, 'validate')

    def test_archive_position(self):
        self.position.action_archive()
        self.assertNotIn(self.position, self.env['account.budget.position'].search([]))

    # -------------------------------------------------------------------------
    # Copy, split, warnings
    # -------------------------------------------------------------------------

    def test_copy_to_next_period(self):
        self._create_line(position_id=self.position.id, date_from='2026-01-01', date_to='2026-02-28')
        self._create_line(position_id=self.revenue_position.id, distribution='at_date', planned_date='2026-06-15')
        self.budget.action_budget_confirm()

        wizard = self.env['account.budget.copy'].create({'budget_id': self.budget.id})
        self.assertEqual((wizard.date_from, wizard.date_to), (date(2027, 1, 1), date(2027, 12, 31)))
        action = wizard.action_copy()
        new_budget = self.env['account.budget'].browse(action['res_id'])

        self.assertEqual(new_budget.state, 'draft')
        lines = new_budget.line_ids.sorted('date_to')
        self.assertEqual([(l.date_from, l.date_to) for l in lines],
                         [(date(2027, 1, 1), date(2027, 2, 28)), (date(2027, 1, 1), date(2027, 12, 31))])
        self.assertEqual(lines[1].planned_date, date(2027, 6, 15))

    def test_split_by_period(self):
        self._create_line(position_id=self.position.id, planned_amount=1200.0)
        self._create_line(position_id=self.revenue_position.id, distribution='at_date', planned_date='2026-08-10')
        wizard = self.env['account.budget.split'].create({'budget_id': self.budget.id, 'period': '3'})
        wizard.action_split()

        expense_lines = self.budget.line_ids.filtered(lambda l: l.budget_type == 'expense').sorted('date_from')
        self.assertEqual([l.date_to for l in expense_lines],
                         [date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31)])
        self.assertAlmostEqual(sum(expense_lines.mapped('planned_amount')), 1200.0)
        revenue_line = self.budget.line_ids.filtered(lambda l: l.budget_type == 'revenue')
        self.assertEqual((revenue_line.date_from, revenue_line.date_to, revenue_line.planned_amount),
                         (date(2026, 7, 1), date(2026, 9, 30), 1000.0))

    def test_warnings(self):
        self.env.company.budget_warning_threshold = 80.0
        line = self._create_line(position_id=self.position.id)
        self.budget.action_budget_confirm()
        self.budget.action_budget_validate()

        def warnings():
            return self.budget.message_ids.filtered(lambda m: 'planned' in (m.body or ''))

        self._create_bill(850.0)
        self.env['account.budget']._cron_warn_budget_responsibles()
        self.assertEqual(line.warning_level, 'threshold')
        self.assertEqual(len(warnings()), 1)
        self.assertIn(self.budget.user_id.partner_id, warnings().partner_ids)

        self.env['account.budget']._cron_warn_budget_responsibles()
        self.assertEqual(len(warnings()), 1, "no second warning for the same level")

        self._create_bill(200.0)
        self.env['account.budget']._cron_warn_budget_responsibles()
        self.assertEqual(line.warning_level, 'exceeded')
        self.assertEqual(len(warnings()), 2)

    # -------------------------------------------------------------------------
    # Control of the expenses
    # -------------------------------------------------------------------------

    def _validated_budget_lines(self):
        department = self._create_line(analytic_account_id=self.analytic_accounts[0].id, planned_amount=1000.0)
        position = self._create_line(position_id=self.position.id, planned_amount=5000.0)
        self.budget.action_budget_confirm()
        self.budget.action_budget_validate()
        return department, position

    def test_bill_budget_warning(self):
        department, _position = self._validated_budget_lines()
        self._create_bill(800.0, analytic_account=self.analytic_accounts[0])

        within = self._create_bill(150.0, analytic_account=self.analytic_accounts[0], post=False)
        self.assertFalse(within.budget_warning)

        over = self._create_bill(300.0, analytic_account=self.analytic_accounts[0], post=False)
        overruns = over._get_budget_overruns()
        self.assertEqual([(overrun['line'], overrun['over']) for overrun in overruns], [(department, 100.0)])
        self.assertIn('over budget', over.budget_warning)
        self.assertIn(department.name, over.budget_warning)

        # the position line counts every bill on its accounts, analytic or not
        big = self._create_bill(4500.0, post=False)
        self.assertEqual([overrun['over'] for overrun in big._get_budget_overruns()], [300.0])

        # outside the period of the budget, a refund, a posted bill: no warning
        self.assertFalse(self._create_bill(9000.0, post=False, move_date='2027-01-05').budget_warning)
        refund = self._create_move('in_refund', 5000.0, self.expense_account, post=False)
        self.assertFalse(refund.budget_warning)
        over.action_post()
        self.assertFalse(over.budget_warning)

    def test_block_documents_over_budget(self):
        self._validated_budget_lines()
        self.env.company.budget_block_documents = True
        accountant = new_test_user(self.env, login='budget_accountant', groups='account.group_account_user',
                                   company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        bill = self._create_bill(1500.0, analytic_account=self.analytic_accounts[0], post=False)
        with self.assertRaises(UserError):
            bill.with_user(accountant).action_post()
        self.assertEqual(bill.state, 'draft')
        # an accounting manager may post it
        bill.action_post()
        self.assertEqual(bill.state, 'posted')

        self.env.company.budget_block_documents = False
        other = self._create_bill(1500.0, analytic_account=self.analytic_accounts[0], post=False)
        other.with_user(accountant).action_post()
        self.assertEqual(other.state, 'posted')

    def test_budget_vs_actual_report(self):
        department, position = self._validated_budget_lines()
        self._create_bill(250.0, analytic_account=self.analytic_accounts[0])
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_budget.report_budget_vs_actual', self.budget.ids)[0].decode()
        self.assertIn('Budget vs Actual', html)
        self.assertIn(department.name, html)
        self.assertIn(position.name, html)
        self.assertIn('Expenses', html)
        self.assertNotIn('Revenues', html)
