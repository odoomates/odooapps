from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanEntries(LoanCommon):

    def test_drawdown_entry(self):
        """ Dr outstanding receipts of the bank journal / Cr long-term loan. """
        loan = self._create_loan()
        operation = self._draw(loan, date(2025, 1, 1), 100000.0)
        move = operation.move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.journal_id, self.bank_journal)
        self.assertEqual(move.date, date(2025, 1, 1))
        self.assertEqual((move.loan_id, move.loan_entry_type), (loan, 'drawdown'))
        self.assertEqual(self._entry(move), {
            self.outstanding_receipts.code: (100000.0, 0.0, 100000.0),
            self.long_term_account.code: (0.0, 100000.0, -100000.0),
        })
        self.assertEqual(move.line_ids.partner_id, self.lender)
        self.assertEqual((loan.drawn_amount, loan.undrawn_amount, loan.outstanding_amount), (100000.0, 0.0, 100000.0))
        with self.assertRaises(UserError):
            self._draw(loan, date(2025, 1, 5), 1.0)

    def test_drawdown_without_outstanding_account(self):
        """ A bank journal without outstanding accounts on its methods takes those of the chart, as payments do;
        the bank posting option goes straight to the bank account. """
        self.bank_journal.inbound_payment_method_line_ids.payment_account_id = False
        loan = self._create_loan()
        move = self._draw(loan).move_id
        chart_account = self.env['account.chart.template'].ref('account_journal_payment_debit_account_id')
        self.assertIn(chart_account, move.line_ids.account_id)
        loan = self._create_loan(bank_posting='bank')
        move = self._draw(loan).move_id
        self.assertIn(self.bank_journal.default_account_id, move.line_ids.account_id)

    def test_payment_entry(self):
        """ Dr long-term loan (principal) + Dr interest / Cr outstanding payments. """
        loan = self._create_loan()
        self._draw(loan)
        line = self._lines(loan)[0]
        move = self._pay(line)
        self.assertEqual(line.state, 'posted')
        self.assertEqual(line.payment_date, date(2025, 2, 1))
        self.assertEqual((move.journal_id, move.date, move.loan_entry_type), (self.bank_journal, line.date, 'payment'))
        self.assertEqual(self._entry(move), {
            self.long_term_account.code: (8106.64, 0.0, 8106.64),
            self.interest_account.code: (500.0, 0.0, 500.0),
            self.outstanding_payments.code: (0.0, 8606.64, -8606.64),
        })
        self.assertEqual(loan.outstanding_amount, 91893.36)
        self.assertEqual(loan.next_line_id, self._lines(loan)[1])

    def test_statement_matches_outstanding(self):
        """ The bank statement line of the payment is matched with the outstanding line of the entry. """
        loan = self._create_loan()
        self._draw(loan)
        move = self._pay(self._lines(loan)[0])
        outstanding = move.line_ids.filtered(lambda aml: aml.account_id == self.outstanding_payments)
        st_line = self.env['account.bank.statement.line'].create({
            'journal_id': self.bank_journal.id, 'date': date(2025, 2, 3), 'payment_ref': loan.name,
            'partner_id': self.lender.id, 'amount': -8606.64})
        self.assertIn(outstanding, self.env['account.move.line'].search(st_line._get_default_amls_matching_domain()))
        _liquidity, suspense, _other = st_line._seek_for_lines()
        st_line.move_id.button_draft()
        suspense.account_id = self.outstanding_payments
        st_line.move_id.action_post()
        (suspense | outstanding).reconcile()
        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(outstanding.reconciled)

    def test_payment_order_and_lock(self):
        loan = self._create_loan()
        self._draw(loan)
        lines = self._lines(loan)
        with self.assertRaises(UserError):
            self._pay(lines[1])
        move = self._pay(lines[0])
        with self.assertRaises(UserError):
            lines[0].principal = 1.0
        with self.assertRaises(UserError):
            move.button_draft()
        with self.assertRaises(UserError):
            move._reverse_moves()
        with self.assertRaises(UserError):
            lines[0].unlink()

    def test_payment_changed_in_wizard(self):
        """ The interest charged by the bank differs: it is paid as charged, the principal stays. """
        loan = self._create_loan()
        self._draw(loan)
        line = self._lines(loan)[0]
        move = self._pay(line, interest=512.5)
        self.assertEqual(line.interest, 512.5)
        self.assertEqual(sum(move.line_ids.mapped('debit')), 8106.64 + 512.5)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal')), 100000.0, places=2)

    def test_cancel_payment(self):
        loan = self._create_loan()
        self._draw(loan)
        lines = self._lines(loan)
        move = self._pay(lines[0])
        self._pay(lines[1])
        self.assertFalse(lines[0].is_last_paid)
        with self.assertRaises(UserError):
            lines[0].action_cancel_payment()
        lines[1].action_cancel_payment()
        lines[0].action_cancel_payment()
        self.assertEqual(lines[0].state, 'draft')
        self.assertFalse(lines[0].move_id)
        self.assertEqual(move.reversal_move_ids.loan_id, loan)
        self.assertEqual(loan.outstanding_amount, 100000.0)
        self.assertEqual(loan._account_balance_at(self.long_term_account, date(2025, 12, 31)), 100000.0)

    def test_tranches(self):
        """ 60,000 drawn, an instalment paid, then 40,000 drawn mid-period: the period counts both balances
        by days, then the unpaid lines repay the 95,136.01 owed. """
        loan = self._create_loan()
        self._draw(loan, date(2025, 1, 1), 60000.0)
        lines = self._lines(loan)
        self.assertEqual(lines[0].opening_balance, 60000.0)
        self.assertEqual((lines[0].interest, lines[0].principal), (300.0, 4863.99))
        self.assertAlmostEqual(sum(lines.mapped('principal')), 60000.0, places=2)
        self._pay(lines[0])
        with self.assertRaises(UserError):
            self._draw(loan, date(2025, 2, 1), 40000.0)
        self._draw(loan, date(2025, 2, 15), 40000.0)
        lines = self._lines(loan)
        self.assertEqual(len(lines), 12)
        self.assertEqual(lines[0].principal, 4863.99, "the paid line is kept")
        self.assertEqual(lines[1].opening_balance, 95136.01)
        self.assertEqual(lines[1].interest, 375.68)
        self.assertEqual(lines[1].amount, 8910.35)
        self.assertEqual(set(lines[1:-1].mapped('amount')), {8910.35})
        self.assertAlmostEqual(sum(lines.mapped('principal')), 100000.0, places=2)
        self.assertEqual(loan.outstanding_amount, 95136.01)

    def test_cancel_drawdown(self):
        loan = self._create_loan()
        first = self._draw(loan, date(2025, 1, 1), 60000.0)
        second = self._draw(loan, date(2025, 1, 10), 40000.0)
        with self.assertRaises(UserError):
            first.action_cancel()
        second.action_cancel()
        self.assertEqual(second.state, 'cancel')
        self.assertEqual(loan.drawn_amount, 60000.0)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal')), 60000.0, places=2)
        self.assertEqual(loan._account_balance_at(self.long_term_account, date(2025, 1, 31)), 60000.0)

    def _pay_three(self):
        loan = self._create_loan()
        self._draw(loan)
        for line in self._lines(loan)[:3]:
            self._pay(line)
        return loan

    def test_early_repayment_lower_instalment(self):
        loan = self._pay_three()
        self.assertEqual(loan.outstanding_amount, 75558.28)
        wizard = self.env['account.loan.repay'].create({'loan_id': loan.id, 'date': date(2025, 4, 15)})
        self.assertEqual(wizard.amount, 75558.28)
        self.assertEqual(wizard.interest, 176.3, "14 days of the April period")
        operation = self._repay(loan, date(2025, 4, 15), 20000.0)
        self.assertEqual(operation.interest, 176.3)
        self.assertEqual(self._entry(operation.move_id), {
            self.long_term_account.code: (20000.0, 0.0, 20000.0),
            self.interest_account.code: (176.3, 0.0, 176.3),
            self.outstanding_payments.code: (0.0, 20176.3, -20176.3),
        })
        lines = self._lines(loan)
        self.assertEqual(loan.payment_count, 12)
        self.assertEqual(len(lines), 12)
        self.assertEqual(lines[3].opening_balance, 55558.28)
        self.assertEqual(lines[3].interest, 148.16, "interest from the repayment only")
        self.assertEqual(lines[3].amount, 6328.5)
        self.assertAlmostEqual(sum(lines.mapped('principal')), 80000.0, places=2)
        self.assertEqual(loan.outstanding_amount, 55558.28)
        with self.assertRaises(UserError):
            self._repay(loan, date(2025, 5, 10), 1000.0)  # the instalment of 1 May is due

    def test_early_repayment_shorter_term(self):
        loan = self._pay_three()
        operation = self._repay(loan, date(2025, 4, 15), 20000.0, after='term')
        lines = self._lines(loan)
        self.assertEqual(loan.payment_count, 10)
        self.assertEqual(len(lines), 10)
        self.assertEqual(lines[3].amount, 8096.43)
        self.assertLessEqual(lines[3].amount, 8606.64)
        self.assertAlmostEqual(sum(lines.mapped('principal')), 80000.0, places=2)
        operation.action_cancel()
        self.assertEqual(loan.payment_count, 12)
        self.assertEqual(len(loan.line_ids), 12)
        self.assertEqual(loan.outstanding_amount, 75558.28)

    def test_full_repayment(self):
        loan = self._pay_three()
        self._repay(loan, date(2025, 4, 15), 75558.28)
        self.assertEqual(loan.state, 'closed')
        self.assertEqual(len(loan.line_ids), 3)
        self.assertEqual(loan.outstanding_amount, 0.0)
        self.assertEqual(loan._account_balance_at(self.long_term_account, date(2025, 4, 30)), 0.0)

    def test_last_payment_closes(self):
        loan = self._create_loan(payment_count=2)
        self._draw(loan)
        for line in self._lines(loan):
            self._pay(line)
        self.assertEqual(loan.state, 'closed')
        self._lines(loan)[-1].action_cancel_payment()
        self.assertEqual(loan.state, 'running')

    def test_floating_rate_change(self):
        """ From 1 July at 8%: the unpaid lines from that date are computed again, the earlier ones stay. """
        loan = self._create_loan(rate_type='floating')
        self._draw(loan)
        before = [(line.principal, line.interest) for line in self._lines(loan)]
        self._pay(self._lines(loan)[0])
        loan.rate_line_ids = [Command.create({'date': date(2025, 7, 1), 'rate': 8.0})]
        lines = self._lines(loan)
        self.assertEqual([(line.principal, line.interest) for line in lines[:6]], before[:6])
        balance = lines[5].closing_balance
        self.assertEqual(lines[6].rate, 8.0)
        self.assertEqual(lines[6].interest, round(balance * 0.08 / 12, 2))
        expected = round(balance * (0.08 / 12) / (1 - (1 + 0.08 / 12) ** -6), 2)
        self.assertEqual(lines[6].amount, expected)
        self.assertAlmostEqual(sum(lines.mapped('principal')), 100000.0, places=2)
        self.assertEqual(loan._rate_at(date(2025, 6, 30)), 6.0)
        self.assertEqual(loan._rate_at(date(2025, 7, 1)), 8.0)
        loan.rate_line_ids.unlink()
        lines = self._lines(loan)
        self.assertEqual(set(lines.mapped('rate')), {6.0})
        self.assertEqual(lines[6].interest, round(balance * 0.06 / 12, 2))
        self.assertAlmostEqual(lines[6].amount, 8606.64, delta=0.02)
        self.assertAlmostEqual(sum(lines.mapped('principal')), 100000.0, places=2)

    def test_floating_rate_actual_days(self):
        """ With the actual days, a rate changing during a period splits it. """
        loan = self._create_loan(
            rate_type='floating', interest_method='actual_365', schedule_method='fixed_principal',
            date_first_payment=date(2025, 1, 31), rate=5.0)
        self._draw(loan)
        loan.rate_line_ids = [Command.create({'date': date(2025, 1, 21), 'rate': 7.3})]
        # 100,000 at 5% from the end of 1 Jan to the end of 20 Jan, then at 7.3% to the end of 31 Jan
        self.assertEqual(self._lines(loan)[0].interest, round(100000 * (0.05 * 19 + 0.073 * 11) / 365, 2))

    def test_reclassification(self):
        """ At two successive dates the short-term account holds the principal due within 12 months. """
        loan = self._create_loan(payment_count=24)
        self._draw(loan)
        lines = self._lines(loan)
        first = self.env['account.loan.reclassify'].create({
            'date': date(2025, 1, 31), 'loan_ids': [Command.set(loan.ids)]}).action_confirm()
        move = self.env['account.move'].search(first['domain'])
        due = round(sum(lines[:12].mapped('principal')), 2)
        self.assertEqual((move.journal_id, move.date, move.loan_entry_type),
                         (self.misc_journal, date(2025, 1, 31), 'reclassification'))
        self.assertEqual(self._entry(move), {
            self.long_term_account.code: (due, 0.0, due),
            self.short_term_account.code: (0.0, due, -due),
        })
        for line in lines[:3]:
            payment = self._pay(line)
        self.assertEqual(self._entry(payment)[self.short_term_account.code][0], lines[2].principal,
                         "the principal reclassified is repaid from the short-term account")
        self.assertNotIn(self.long_term_account.code, self._entry(payment))
        self.env['account.loan.reclassify'].create({
            'date': date(2025, 4, 30), 'loan_ids': [Command.set(loan.ids)]}).action_confirm()
        second = loan.move_ids.filtered(lambda m: m.loan_entry_type == 'reclassification' and m != move)
        self.assertAlmostEqual(sum(second.line_ids.mapped('debit')), sum(lines[12:15].mapped('principal')), places=2)
        self.assertAlmostEqual(loan._account_balance_at(self.short_term_account, date(2025, 4, 30)),
                               sum(lines[3:15].mapped('principal')), places=2)
        self.assertAlmostEqual(
            loan._account_balance_at(self.short_term_account, date(2025, 4, 30))
            + loan._account_balance_at(self.long_term_account, date(2025, 4, 30)),
            loan.outstanding_amount, places=2)
        with self.assertRaises(UserError):
            # nothing to move again
            self.env['account.loan.reclassify'].create({
                'date': date(2025, 4, 30), 'loan_ids': [Command.set(loan.ids)]}).action_confirm()
        with self.assertRaises(UserError):
            loan._reclassify(date(2025, 3, 31))
        # a reclassification may be reversed in the books: the loan follows it
        second._reverse_moves([{'date': second.date}], cancel=True)
        self.assertAlmostEqual(loan._account_balance_at(self.short_term_account, date(2025, 4, 30)),
                               sum(lines[3:12].mapped('principal')), places=2)

    def test_reclassification_near_maturity(self):
        """ Within the last 12 months the whole principal is current. """
        loan = self._create_loan()
        self._draw(loan)
        move = loan._reclassify(date(2025, 1, 31))
        self.assertEqual(sum(move.line_ids.mapped('debit')), 100000.0)

    def test_foreign_currency(self):
        """ A loan in a foreign currency posts its amount in currency and the company value of the day. """
        eur = self.setup_other_currency('EUR', rates=[('2025-01-01', 2.0)])
        loan = self._create_loan(currency_id=eur.id, principal=10000.0)
        move = self._draw(loan).move_id
        self.assertEqual(move.line_ids.currency_id, eur)
        self.assertEqual(self._entry(move), {
            self.outstanding_receipts.code: (5000.0, 0.0, 10000.0),
            self.long_term_account.code: (0.0, 5000.0, -10000.0),
        })
        payment = self._pay(self._lines(loan)[0])
        self.assertEqual(self._entry(payment), {
            self.long_term_account.code: (405.33, 0.0, 810.66),
            self.interest_account.code: (25.0, 0.0, 50.0),
            self.outstanding_payments.code: (0.0, 430.33, -860.66),
        })
        report = self.env['account.loan.report'].create({'date': date(2025, 2, 1)})
        report._compute_lines()
        line = report.line_ids.filtered(lambda line: line.loan_id == loan)
        self.assertEqual(line.outstanding, 9189.34)
        self.assertEqual(line.outstanding_company, 4594.67)
        bank_gbp = self.env['account.journal'].create({
            'name': 'Bank GBP', 'code': 'BGBP', 'type': 'bank',
            'currency_id': self.setup_other_currency('GBP').id})
        with self.assertRaises(UserError):
            loan.bank_journal_id = bank_gbp
