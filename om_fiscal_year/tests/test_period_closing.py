from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPeriodClosing(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'fiscalyear_lock_date': False, 'sale_lock_date': False, 'purchase_lock_date': False})
        cls.env['account.period.closing.task'].search([]).active = False
        cls.task = cls.env['account.period.closing.task'].create({'name': 'Accrue the electricity'})

    def _closing(self, **values):
        return self.env['account.period.closing'].create({'date_from': date(2026, 3, 1), **values})

    def _check(self, closing, code):
        return closing.check_ids.filtered(lambda check: check.code == code)

    def test_checklist_and_close(self):
        draft = self.init_invoice('out_invoice', amounts=[100.0], taxes=[], invoice_date='2026-03-10')
        closing = self._closing()
        self.assertEqual(closing.name, 'March 2026')
        self.assertEqual(closing.date_to, date(2026, 3, 31))
        self.assertEqual(self._check(closing, 'draft_entries').status, 'blocking')
        self.assertEqual(self._check(closing, 'draft_entries').count, 1)
        task = closing.check_ids.filtered('is_manual')
        self.assertEqual((task.name, task.status), ('Accrue the electricity', 'todo'))
        action = self._check(closing, 'draft_entries').action_open()
        self.assertEqual(self.env['account.move'].search(action['domain']), draft)

        with self.assertRaises(UserError):
            closing.action_close()
        draft.action_post()
        with self.assertRaises(UserError):
            # the task is not done
            closing.action_close()
        task.action_mark_done()
        self.assertEqual((task.status, task.done_by_id), ('done', self.env.user))
        closing.action_close()
        self.assertEqual(self._check(closing, 'draft_entries').status, 'ok')
        self.assertEqual(closing.state, 'closed')
        self.assertEqual(self.company.fiscalyear_lock_date, date(2026, 3, 31))
        with self.assertRaises(UserError):
            task.action_mark_todo()

        closing.action_reopen()
        self.assertEqual(closing.state, 'open')
        self.assertFalse(self.company.fiscalyear_lock_date)

    def test_lock_sales_and_purchases_and_later_periods(self):
        self.task.active = False
        self.company.purchase_lock_date = date(2026, 1, 31)
        march = self._closing(lock_type='sale_purchase')
        march.action_close()
        self.assertEqual((self.company.sale_lock_date, self.company.purchase_lock_date),
                         (date(2026, 3, 31), date(2026, 3, 31)))
        self.assertFalse(self.company.fiscalyear_lock_date)
        april = self._closing(date_from=date(2026, 4, 1), lock_type='none')
        april.action_close()
        with self.assertRaises(UserError):
            march.action_reopen()
        april.action_reopen()
        march.action_reopen()
        self.assertEqual((self.company.sale_lock_date, self.company.purchase_lock_date), (False, date(2026, 1, 31)))

        with self.assertRaises(ValidationError):
            self._closing(date_from=date(2026, 3, 15))

    def test_warnings(self):
        self.task.active = False
        bank = self.company_data['default_journal_bank']
        # a payment leaving the bank account negative
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2026-03-05',
            'line_ids': [
                Command.create({'name': 'rent', 'account_id': bank.default_account_id.id, 'balance': -500.0}),
                Command.create({'name': 'rent', 'account_id': self.company_data['default_account_expense'].id,
                                'balance': 500.0}),
            ],
        }).action_post()
        # the same bill entered twice
        for _index in range(2):
            self.init_invoice('in_invoice', amounts=[80.0], taxes=[],
                              invoice_date='2026-03-12', post=True).ref = 'SUP-001'
        # a bank transaction not reconciled
        self.env['account.bank.statement.line'].create({
            'journal_id': bank.id, 'date': '2026-03-20', 'payment_ref': 'unknown', 'amount': 42.0,
        })

        closing = self._closing(lock_type='tax')
        self.assertEqual(self._check(closing, 'negative_cash').status, 'warning')
        self.assertEqual(self._check(closing, 'duplicate_bills').count, 2)
        self.assertEqual(self._check(closing, 'unreconciled_bank').status, 'warning')
        closing.action_close()
        self.assertEqual(self.company.tax_lock_date, date(2026, 3, 31))

        # the global lock is refused with unreconciled bank transactions: the check blocks
        april = self._closing(date_from=date(2026, 4, 1))
        self.assertEqual(self._check(april, 'unreconciled_bank').status, 'blocking')

    def test_default_tasks(self):
        tasks = self.env['account.period.closing.task'].with_context(active_test=False).search(
            [('id', 'in', [self.env.ref('om_fiscal_year.%s' % xmlid).id for xmlid in (
                'closing_task_bank', 'closing_task_accruals', 'closing_task_review')])])
        self.assertEqual(len(tasks), 3)
        self.assertFalse(tasks.company_id)

    def test_only_administrators_close(self):
        self.task.active = False
        accountant = new_test_user(self.env, login='closing_accountant', groups='account.group_account_user')
        closing = self._closing().with_user(accountant)
        closing.action_refresh()
        with self.assertRaises(UserError):
            closing.action_close()
