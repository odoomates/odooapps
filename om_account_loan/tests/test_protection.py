from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanProtection(LoanCommon):
    """ The schedule protects itself: what the loan posted is changed from the loan only. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoicing = new_test_user(
            cls.env, login='loan_protect_invoicing', groups='account.group_account_invoice',
            company_id=cls.env.company.id)

    def _paid_loan(self):
        loan = self._create_loan()
        self._draw(loan)
        line = self._lines(loan)[0]
        self._pay(line)
        return loan, line

    def test_client_context_does_not_bypass(self):
        """ The markers of the loan are objects: a context value sent by a client does not unlock its entries. """
        loan, line = self._paid_loan()
        move = line.move_id
        for env_user in (self.env.user, self.invoicing):
            entry = move.with_user(env_user).with_context(loan_reverse=True)
            with self.assertRaises(UserError):
                entry.button_draft()
            with self.assertRaises(UserError):
                entry.button_cancel()
        with self.assertRaises(UserError):
            line.with_context(loan_schedule_update=True).write({'principal': 1.0})
        with self.assertRaises(UserError):
            line.with_context(loan_schedule_update=True).write({'state': 'draft'})
        self.assertEqual((move.state, line.state, line.move_id), ('posted', 'posted', move))

    def test_entries_stay_linked(self):
        loan, line = self._paid_loan()
        with self.assertRaises(UserError):
            line.move_id.write({'loan_id': False})
        with self.assertRaises(UserError):
            loan.write({'move_ids': [Command.clear()]})
        other = self._create_loan()
        with self.assertRaises(UserError):
            line.write({'loan_id': other.id})
        self.assertTrue(loan._has_entries())

    def test_posted_operation_locked(self):
        loan = self._create_loan()
        drawdown = self._draw(loan)
        for vals in ({'amount': 1.0}, {'state': 'cancel'}, {'date': date(2025, 1, 2)}):
            with self.assertRaises(UserError):
                drawdown.write(vals)
        self.assertEqual(loan.outstanding_amount, 100000.0)

    def test_terms_and_accounts_locked(self):
        loan = self._create_loan()
        # running without entries: the terms are fixed, the accounts not yet
        with self.assertRaises(UserError):
            loan.principal = 5.0
        with self.assertRaises(UserError):
            loan.loan_type = 'lease'
        loan.account_long_term_id = self.long_term_account
        self._draw(loan)
        with self.assertRaises(UserError):
            loan.account_long_term_id = self.interest_account
        with self.assertRaises(UserError):
            loan.partner_id = self.lessor
        # the rate and the number of payments too: a rate change or an early repayment changes them
        with self.assertRaises(UserError):
            loan.rate = 7.0
        with self.assertRaises(UserError):
            loan.rate_type = 'floating'
        with self.assertRaises(UserError):
            loan.payment_count = 24

    def test_reclassifications_listed_with_the_operations(self):
        """ The Operations tab lists the reclassifications, with the principal they moved. """
        loan = self._create_loan()
        self._draw(loan)
        move = loan._reclassify(date(2025, 1, 31))
        self.assertEqual(loan.reclassification_move_ids, move)
        # the twelve instalments are due within 12 months: the whole principal moves to the short term
        self.assertEqual(move.loan_reclassified_amount, 100000.0)
        self.assertFalse(loan.operation_ids.filtered(lambda op: op.move_id == move))

    def test_rate_change_of_a_fixed_rate_loan(self):
        """ A fixed rate renegotiated with the lender: a dated rate change, the paid instalments stay. """
        loan, _line = self._paid_loan()
        before = self._lines(loan)[0].interest
        loan.rate_line_ids = [Command.create({'date': date(2025, 3, 1), 'rate': 7.5})]
        lines = self._lines(loan)
        self.assertEqual(loan.rate_type, 'fixed')
        self.assertEqual(lines[0].interest, before)
        self.assertEqual(lines[0].rate, 6.0)
        self.assertEqual(lines[2].rate, 7.5)
        self.assertEqual(loan._rate_at(date(2025, 3, 1)), 7.5)
        self.assertAlmostEqual(sum(lines.mapped('principal')), 100000.0, places=2)

    def test_lock_date_refused(self):
        """ A loan entry is not posted on another date than its schedule: a locked period is refused. """
        loan = self._create_loan()
        self._draw(loan)
        self.env.company.fiscalyear_lock_date = date(2025, 3, 31)
        line = self._lines(loan)[0]
        with self.assertRaises(UserError):
            self._pay(line)
        self.assertEqual(line.state, 'draft')
        with self.assertRaises(UserError):
            self._draw(self._create_loan(), date(2025, 1, 15))
        # after the lock date
        self.env.company.fiscalyear_lock_date = False
        move = self._pay(line)
        self.assertEqual(move.date, date(2025, 2, 1))
        self.env.company.fiscalyear_lock_date = date(2025, 3, 31)
        with self.assertRaises(UserError):
            line.action_cancel_payment()
        self.assertEqual(line.state, 'posted')

    def test_cancelled_drawdown_frees_the_loan(self):
        loan = self._create_loan()
        self._draw(loan).action_cancel()
        self.assertFalse(loan._has_entries())
        loan.action_cancel()
        self.assertEqual(loan.state, 'cancel')
        loan.action_draft()
        loan.unlink()

    def test_pay_wizard_checks(self):
        loan = self._create_loan()
        self._draw(loan)
        line = self._lines(loan)[0]
        with self.assertRaises(UserError):
            self._pay(line, interest=-50.0)
        with self.assertRaises(UserError):
            self._pay(line, day=date(2024, 12, 31))
        self._pay(line, day=date(2025, 2, 10))
        with self.assertRaises(UserError):
            self._pay(self._lines(loan)[1], day=date(2025, 2, 5))
        # without a withholding tax, nothing is withheld whatever the wizard says
        move = self._pay(self._lines(loan)[1], withholding=5.0)
        self.assertEqual(self._lines(loan)[1].withholding, 0.0)
        self.assertNotIn(self.withholding_account, move.line_ids.account_id)

    def test_pay_needs_a_drawdown(self):
        loan = self._create_loan()
        line = self._lines(loan)[0]
        self.assertFalse(line.is_next)
        with self.assertRaises(UserError):
            self._pay(line)
        self._draw(loan)
        self.assertEqual(loan.line_ids.filtered('is_next'), line)

    def test_draft_lease_without_payment(self):
        lease = self._create_lease(confirm=False, lease_payment=0.0)
        self.assertEqual(lease.principal, 0.0)
        with self.assertRaises(UserError):
            lease.action_confirm()
        lease.lease_payment = 1000.0
        lease.action_confirm()
        self.assertEqual(lease.state, 'running')

    def test_draft_bill_must_match(self):
        lease = self._create_lease(bill_posting='draft')
        line = self._lines(lease)[0]
        bill = line._create_bill()
        self.assertEqual(bill.state, 'draft')
        bill.invoice_line_ids[0].price_unit = 1.0
        with self.assertRaises(UserError):
            bill.action_post()
        bill.invoice_line_ids[0].price_unit = line.principal
        bill.action_post()
        self.assertEqual(bill.state, 'posted')

    def test_rate_change_after_paid(self):
        loan = self._create_loan(rate_type='floating')
        self._draw(loan)
        self._pay(self._lines(loan)[0])
        with self.assertRaises(ValidationError):
            loan.rate_line_ids = [Command.create({'date': date(2025, 1, 15), 'rate': 8.0})]
        loan.rate_line_ids = [Command.create({'date': date(2025, 2, 2), 'rate': 8.0})]
        self.assertEqual(self._lines(loan)[1].rate, 8.0)

    def test_reclassify_not_in_the_future(self):
        loan = self._create_loan()
        self._draw(loan)
        wizard = self.env['account.loan.reclassify'].create({
            'date': date(2999, 12, 31), 'loan_ids': [Command.set(loan.ids)]})
        with self.assertRaises(UserError):
            wizard.action_confirm()
