from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.om_account_loan.models.account_loan import annuity, annuity_count

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanSchedule(LoanCommon):

    def test_annuity_formula(self):
        self.assertAlmostEqual(annuity(100000.0, 0.005, 12), 8606.64, places=2)
        self.assertAlmostEqual(annuity(1200.0, 0.0, 12), 100.0)
        self.assertEqual(annuity_count(100000.0, 0.005, 8606.65), 12)
        self.assertEqual(annuity_count(1200.0, 0.0, 100.0), 12)
        self.assertIsNone(annuity_count(100000.0, 0.005, 500.0), "the instalment only pays the interest")

    def test_reference_from_sequence(self):
        loan = self._create_loan(confirm=False)
        self.assertTrue(loan.name.startswith('LOAN/2025/'))

    def test_annuity_schedule(self):
        """ 100,000 at 6% over 12 monthly payments: 8,606.64 a month, the residue on the last one. """
        loan = self._create_loan()
        lines = self._lines(loan)
        self.assertEqual(len(lines), 12)
        self.assertEqual(lines[0].date, date(2025, 2, 1))
        self.assertEqual(lines[-1].date, date(2026, 1, 1))
        self.assertEqual(lines[0].opening_balance, 100000.0)
        self.assertEqual(lines[0].interest, 500.0)
        self.assertEqual(lines[0].principal, 8106.64)
        self.assertEqual(lines[1].interest, 459.47)
        self.assertEqual(set(lines[:-1].mapped('amount')), {8606.64})
        self.assertEqual(lines[-1].principal, 8563.87)
        self.assertEqual(lines[-1].interest, 42.82)
        self.assertEqual(lines[-1].amount, 8606.69, "the rounding residue goes on the last line")
        self.assertAlmostEqual(sum(lines.mapped('principal')), 100000.0, places=2)
        self.assertAlmostEqual(sum(lines.mapped('interest')), 3279.73, places=2)
        self.assertEqual(lines[-1].closing_balance, 0.0)
        for previous, line in zip(lines, lines[1:], strict=False):
            self.assertEqual(line.opening_balance, previous.closing_balance)
        self.assertEqual(loan.next_date, date(2025, 2, 1))
        self.assertEqual(loan.date_end, date(2026, 1, 1))

    def test_fixed_principal(self):
        loan = self._create_loan(principal=120000.0, schedule_method='fixed_principal')
        lines = self._lines(loan)
        self.assertEqual(set(lines.mapped('principal')), {10000.0})
        self.assertEqual(lines[:3].mapped('interest'), [600.0, 550.0, 500.0])
        self.assertEqual(lines[-1].interest, 50.0)

    def test_rounding_residue(self):
        loan = self._create_loan(schedule_method='fixed_principal', payment_count=3, rate=0.0)
        self.assertEqual(self._lines(loan).mapped('principal'), [33333.33, 33333.33, 33333.34])

    def test_calendar_months(self):
        """ A first payment on the last day of a month keeps the payments on the last day of the months. """
        loan = self._create_loan(date_start=date(2023, 12, 31), date_first_payment=date(2024, 1, 31))
        self.assertEqual(self._lines(loan)[:4].mapped('date'), [
            date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30)])
        loan = self._create_loan(date_start=date(2024, 12, 31), date_first_payment=date(2025, 1, 31))
        self.assertEqual(self._lines(loan)[1].date, date(2025, 2, 28))
        loan = self._create_loan(date_start=date(2024, 12, 15), date_first_payment=date(2025, 1, 15),
                                 payment_frequency='quarterly', payment_count=4)
        self.assertEqual(self._lines(loan).mapped('date'), [
            date(2025, 1, 15), date(2025, 4, 15), date(2025, 7, 15), date(2025, 10, 15)])

    def test_first_payment_default(self):
        loan = self.env['account.loan'].create({
            'partner_id': self.lender.id, 'principal': 1000.0, 'date_start': date(2025, 1, 1),
            'payment_frequency': 'semiannual'})
        self.assertEqual(loan.date_first_payment, date(2025, 7, 1))
        loan.date_start = date(2025, 1, 31)
        self.assertEqual(loan.date_first_payment, date(2025, 7, 31))
        with self.assertRaises(ValidationError):
            loan.date_first_payment = date(2025, 1, 1)

    def test_broken_first_period(self):
        """ A first period shorter than a period counts its days. """
        loan = self._create_loan(date_start=date(2025, 1, 16), date_first_payment=date(2025, 1, 31))
        # 15 days of the 31 days from 31 December to 31 January
        self.assertEqual(self._lines(loan)[0].interest, round(100000 * 0.06 / 12 * 15 / 31, 2))

    def test_actual_365(self):
        loan = self._create_loan(rate=5.0, interest_method='actual_365', date_first_payment=date(2025, 1, 31),
                                 schedule_method='fixed_principal', payment_count=10)
        lines = self._lines(loan)
        self.assertEqual(lines[0].interest, 410.96, "100,000 x 5% x 30 / 365")
        self.assertEqual(lines[1].interest, round(90000 * 0.05 * 28 / 365, 2))
        self.assertEqual(lines[2].interest, round(80000 * 0.05 * 31 / 365, 2))

    def test_edit_unpaid_line(self):
        """ A principal changed by hand moves the difference to the last line; a recompute discards it. """
        loan = self._create_loan()
        lines = self._lines(loan)
        lines[1].principal = 10000.0
        self.assertEqual(lines[2].opening_balance, lines[1].closing_balance)
        self.assertAlmostEqual(sum(lines.mapped('principal')), 100000.0, places=2)
        self.assertAlmostEqual(lines[-1].principal, 8563.87 - (10000.0 - 8147.17), places=2)
        lines[3].date = date(2025, 5, 5)
        self.assertEqual(lines[3].date, date(2025, 5, 5))
        with self.assertRaises(UserError):
            lines[-2].principal = 100000.0
        loan.action_compute_schedule()
        self.assertEqual(lines[1].principal, 8147.17)
        self.assertEqual(lines[3].date, date(2025, 5, 1))

    def test_terms_locked_after_entries(self):
        loan = self._create_loan()
        loan.principal = 90000.0
        self._draw(loan)
        with self.assertRaises(UserError):
            loan.principal = 80000.0
        with self.assertRaises(UserError):
            loan.unlink()

    def test_configuration_required(self):
        loan = self._create_loan(confirm=False, account_interest_id=False)
        with self.assertRaises(UserError):
            loan.action_confirm()
        with self.assertRaises(ValidationError):
            loan.account_short_term_id = self.long_term_account
        with self.assertRaises(ValidationError):
            loan.account_long_term_id = self.company_data['default_account_payable']

    def test_cancel_and_reset(self):
        loan = self._create_loan()
        loan.action_cancel()
        self.assertEqual(loan.state, 'cancel')
        loan.action_draft()
        self.assertEqual(loan.state, 'draft')
        self.assertFalse(loan.line_ids)
        loan.unlink()
