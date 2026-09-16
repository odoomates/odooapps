from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestYearEndClosing(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.retained_earnings = cls.env['account.account'].create({
            'code': 'RETEARN', 'name': 'Retained Earnings', 'account_type': 'equity',
        })
        cls.unaffected_earnings = cls.company.get_unaffected_earnings_account()
        cls.fy_2025 = cls._create_fiscal_year(2025)
        cls._create_invoice_for_year('out_invoice', 1000.0, '2025-06-01')
        cls._create_invoice_for_year('in_invoice', 400.0, '2025-07-01')

    @classmethod
    def _create_fiscal_year(cls, year):
        return cls.env['account.fiscal.year'].create({
            'name': str(year), 'date_from': date(year, 1, 1), 'date_to': date(year, 12, 31),
        })

    @classmethod
    def _create_invoice_for_year(cls, move_type, amount, invoice_date, post=True):
        return cls.init_invoice(move_type, amounts=[amount], invoice_date=invoice_date, taxes=[], post=post)

    def _close(self, fiscal_year, lock=True, **values):
        wizard = self.env['account.fiscal.year.closing'].with_context(default_fiscal_year_id=fiscal_year.id).create({
            'retained_earnings_account_id': self.retained_earnings.id,
            'lock': lock,
            **values,
        })
        wizard.action_close()
        return wizard

    def _balance(self, account, date_to):
        [(balance,)] = self.env['account.move.line']._read_group([
            ('account_id', '=', account.id), ('parent_state', '=', 'posted'), ('date', '<=', date_to),
        ], aggregates=['balance:sum'])
        return balance or 0.0

    def _profit_and_loss(self, date_from, date_to):
        [(balance,)] = self.env['account.move.line']._read_group([
            ('company_id', '=', self.company.id), ('parent_state', '=', 'posted'),
            ('date', '>=', date_from), ('date', '<=', date_to),
            ('account_id.internal_group', 'in', ('income', 'expense')),
        ], aggregates=['balance:sum'])
        return -(balance or 0.0)

    def test_close_transfers_profit_to_retained_earnings(self):
        wizard = self.env['account.fiscal.year.closing'].with_context(default_fiscal_year_id=self.fy_2025.id).create({
            'retained_earnings_account_id': self.retained_earnings.id,
        })
        self.assertEqual(wizard.earnings, 600.0)
        self.assertEqual(wizard.date, date(2026, 1, 1))
        self.assertEqual(wizard.journal_id.type, 'general')
        self.assertFalse(wizard.blocking_issues)
        wizard.action_close()

        closing_move = self.fy_2025.closing_move_id
        self.assertEqual(self.fy_2025.state, 'closed')
        self.assertEqual(closing_move.state, 'posted')
        self.assertEqual(closing_move.date, date(2026, 1, 1))
        self.assertRecordValues(closing_move.line_ids.sorted('balance'), [
            {'account_id': self.retained_earnings.id, 'balance': -600.0},
            {'account_id': self.unaffected_earnings.id, 'balance': 600.0},
        ])
        # the closed year keeps its figures, and nothing is left to allocate afterwards
        self.assertEqual(self._profit_and_loss('2025-01-01', '2025-12-31'), 600.0)
        self.assertEqual(self._balance(self.retained_earnings, '2025-12-31'), 0.0)
        self.assertEqual(self._balance(self.retained_earnings, '2026-01-01'), -600.0)
        self.assertEqual(self.company.fiscalyear_lock_date, date(2025, 12, 31))
        self.assertEqual(self.company.retained_earnings_account_id, self.retained_earnings)

    def test_close_a_loss(self):
        self._create_invoice_for_year('in_invoice', 900.0, '2025-08-01')
        self._close(self.fy_2025, lock=False)
        self.assertRecordValues(self.fy_2025.closing_move_id.line_ids.sorted('balance'), [
            {'account_id': self.unaffected_earnings.id, 'balance': -300.0},
            {'account_id': self.retained_earnings.id, 'balance': 300.0},
        ])

    def test_consecutive_years_and_earlier_open_years(self):
        fy_2024 = self._create_fiscal_year(2024)
        self._create_invoice_for_year('out_invoice', 100.0, '2024-03-01')
        fy_2026 = self._create_fiscal_year(2026)
        self._create_invoice_for_year('out_invoice', 50.0, '2026-02-01')

        wizard = self.env['account.fiscal.year.closing'].with_context(default_fiscal_year_id=self.fy_2025.id).create({
            'retained_earnings_account_id': self.retained_earnings.id,
        })
        self.assertEqual(wizard.open_previous_year_count, 1)
        # the earnings of 2024 were never transferred: they are included
        self.assertEqual(wizard.earnings, 700.0)
        wizard.action_close()

        self._close(fy_2026)
        self.assertEqual(sum(fy_2026.closing_move_id.line_ids.filtered(
            lambda line: line.account_id == self.retained_earnings).mapped('balance')), -50.0)
        self.assertEqual(self._balance(self.retained_earnings, '2027-01-01'), -750.0)
        self.assertEqual(fy_2024.state, 'open')

    def test_blocking_issues(self):
        draft = self._create_invoice_for_year('out_invoice', 10.0, '2025-12-20', post=False)
        wizard = self.env['account.fiscal.year.closing'].with_context(default_fiscal_year_id=self.fy_2025.id).create({
            'retained_earnings_account_id': self.retained_earnings.id,
        })
        self.assertEqual(wizard.draft_move_count, 1)
        self.assertTrue(wizard.blocking_issues)
        with self.assertRaises(UserError):
            wizard.action_close()
        draft.unlink()

        self.env['account.bank.statement.line'].create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'date': '2025-12-15', 'payment_ref': 'unmatched', 'amount': 100.0,
        })
        wizard.invalidate_recordset()
        self.assertEqual(wizard.unreconciled_statement_line_count, 1)
        self.assertTrue(wizard.blocking_issues)
        with self.assertRaises(UserError):
            wizard.action_close()

        # closing without locking is allowed with unreconciled bank transactions
        wizard.lock = False
        self.assertFalse(wizard.blocking_issues)
        wizard.action_close()
        self.assertEqual(self.fy_2025.state, 'closed')
        self.assertFalse(self.company.fiscalyear_lock_date)

    def test_reopen_reverses_the_closing(self):
        self._close(self.fy_2025)
        closing_move = self.fy_2025.closing_move_id
        self.fy_2025.action_reopen()

        self.assertEqual(self.fy_2025.state, 'open')
        self.assertFalse(self.fy_2025.closing_move_id)
        self.assertEqual(closing_move.reversal_move_ids.state, 'posted')
        self.assertEqual(self._balance(self.retained_earnings, '2026-01-01'), 0.0)

        self._close(self.fy_2025)
        self.assertEqual(self._balance(self.retained_earnings, '2026-01-01'), -600.0)

    def test_closed_year_is_protected(self):
        self._close(self.fy_2025, lock=False)
        with self.assertRaises(UserError):
            self.fy_2025.date_to = date(2025, 11, 30)
        with self.assertRaises(UserError):
            self.fy_2025.unlink()
        with self.assertRaises(UserError):
            self._close(self.fy_2025, lock=False)
        self.fy_2025.name = 'FY 2025'

    def test_closing_entry_changes_only_through_reopen(self):
        self._close(self.fy_2025, lock=False)
        closing_move = self.fy_2025.closing_move_id
        with self.assertRaises(UserError):
            closing_move.button_draft()
        with self.assertRaises(UserError):
            closing_move.button_cancel()
        with self.assertRaises(UserError):
            closing_move.unlink()
        self.fy_2025.action_reopen()
        closing_move.button_draft()
        closing_move.unlink()

    def test_nothing_to_transfer(self):
        fy_2023 = self._create_fiscal_year(2023)
        self._close(fy_2023, lock=False)
        self.assertEqual(fy_2023.state, 'closed')
        self.assertFalse(fy_2023.closing_move_id)

    def test_only_administrators_close(self):
        accountant = new_test_user(self.env, login='fy_accountant', groups='account.group_account_user')
        with self.assertRaises(UserError):
            self.fy_2025.with_user(accountant).action_open_closing_wizard()
        with self.assertRaises(UserError):
            self.fy_2025.with_user(accountant).action_reopen()

    def test_account_types(self):
        with self.assertRaises(UserError):
            self._close(self.fy_2025, lock=False, retained_earnings_account_id=self.unaffected_earnings.id)

        other_unaffected = self.unaffected_earnings.copy({'code': 'PLAPPR2', 'name': 'Other Appropriation'})
        self._close(self.fy_2025, lock=False, unaffected_earnings_account_id=other_unaffected.id)
        self.assertEqual(
            self.fy_2025.closing_move_id.line_ids.filtered(lambda line: line.balance > 0).account_id, other_unaffected)

    def test_lock_date_settings_update_their_own_lock_date(self):
        settings = Form(self.env['res.config.settings'])
        settings.sale_lock_date = date(2025, 3, 31)
        settings.purchase_lock_date = date(2025, 4, 30)
        settings.tax_lock_date = date(2025, 5, 31)
        settings.save().execute()
        self.assertEqual(self.company.sale_lock_date, date(2025, 3, 31))
        self.assertEqual(self.company.purchase_lock_date, date(2025, 4, 30))
        self.assertEqual(self.company.tax_lock_date, date(2025, 5, 31))
        self.assertFalse(self.company.hard_lock_date)

    def test_multi_company_rule(self):
        company_2 = self.setup_other_company()['company']
        fy_other = self.env['account.fiscal.year'].create({
            'name': 'Other 2025', 'date_from': date(2025, 1, 1), 'date_to': date(2025, 12, 31),
            'company_id': company_2.id,
        })
        user = new_test_user(
            self.env, login='fy_company_1', groups='account.group_account_manager',
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)],
        )
        found = self.env['account.fiscal.year'].with_user(user).search([])
        self.assertIn(self.fy_2025, found)
        self.assertNotIn(fy_other, found)
