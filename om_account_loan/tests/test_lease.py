from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLease(LoanCommon):

    def _payment_term_line(self, bill):
        return bill.line_ids.filtered(lambda aml: aml.display_type == 'payment_term')

    def test_present_value(self):
        """ The lease liability is the present value of the payments at the rate of the lease. """
        lease = self._create_lease(confirm=False)
        self.assertEqual(lease.principal, 11618.93)
        self.assertTrue(lease.name.startswith('LEASE/'))
        self.assertEqual(lease.account_long_term_id, self.lease_long_term_account)
        self.assertEqual(lease.account_short_term_id, self.lease_short_term_account)
        lease.rate = 0.0
        self.assertEqual(lease.principal, 12000.0)
        lease.rate = 6.0
        lease.action_compute_schedule()
        lines = self._lines(lease)
        self.assertEqual(len(lines), 12)
        self.assertEqual(set(lines.mapped('amount')), {1000.0})
        self.assertEqual((lines[0].opening_balance, lines[0].interest, lines[0].principal), (11618.93, 58.09, 941.91))
        self.assertEqual((lines[1].interest, lines[1].principal), (53.39, 946.61))
        self.assertEqual((lines[-1].interest, lines[-1].principal, lines[-1].closing_balance), (4.98, 995.02, 0.0))
        self.assertEqual(lease.lease_end, date(2026, 1, 1))

    def test_paid_in_advance(self):
        """ A first payment on the start date is not discounted: it repays the liability only. """
        lease = self._create_lease(date_first_payment=date(2025, 1, 1))
        self.assertEqual(lease.principal, 11677.03)
        lines = self._lines(lease)
        self.assertEqual((lines[0].date, lines[0].interest, lines[0].principal), (date(2025, 1, 1), 0.0, 1000.0))
        self.assertEqual((lines[1].interest, lines[1].principal), (53.39, 946.61))
        self.assertEqual(lines[-1].closing_balance, 0.0)
        self.assertEqual(lease.lease_end, date(2026, 1, 1))
        bill = lines[0]._create_bill()
        self.assertEqual(bill.invoice_date, date(2025, 1, 1))
        self.assertEqual(self._payment_term_line(bill).credit, 1000.0)

    def test_initial_recognition(self):
        """ Dr right-of-use asset / Cr long-term lease liability at the present value, on the start date. """
        lease = self._create_lease()
        operation = lease.operation_ids
        self.assertEqual((operation.operation_type, operation.amount, operation.date),
                         ('recognition', 11618.93, date(2025, 1, 1)))
        move = operation.move_id
        self.assertEqual((move.journal_id, move.date, move.state), (self.misc_journal, date(2025, 1, 1), 'posted'))
        self.assertEqual((move.loan_id, move.loan_entry_type), (lease, 'recognition'))
        self.assertEqual(self._entry(move), {
            self.rou_account.code: (11618.93, 0.0, 11618.93),
            self.lease_long_term_account.code: (0.0, 11618.93, -11618.93),
        })
        self.assertEqual(move.line_ids.partner_id, self.lessor)
        self.assertEqual(lease.state, 'running')
        self.assertEqual((lease.drawn_amount, lease.outstanding_amount), (11618.93, 11618.93))
        with self.assertRaises(UserError):
            move.button_draft()

    def test_lease_bill(self):
        """ A due line creates the bill of the lessor: Dr lease liability + Dr interest / Cr payable. """
        lease = self._create_lease()
        line = self._lines(lease)[0]
        action = line.action_create_bill()
        bill = line.move_id
        self.assertEqual(action['res_id'], bill.id)
        self.assertEqual((bill.move_type, bill.state, bill.partner_id), ('in_invoice', 'posted', self.lessor))
        self.assertEqual((bill.journal_id, bill.invoice_date), (self.purchase_journal, date(2025, 2, 1)))
        self.assertEqual((bill.loan_id, bill.loan_entry_type), (lease, 'bill'))
        self.assertEqual(bill.amount_total, 1000.0)
        products = bill.invoice_line_ids
        self.assertEqual(
            sorted((aml.account_id, aml.debit) for aml in products),
            sorted([(self.lease_long_term_account, 941.91), (self.interest_account, 58.09)]))
        self.assertEqual(self._payment_term_line(bill).credit, 1000.0)
        self.assertEqual((line.state, line.payment_date, line.bill_status), ('posted', date(2025, 2, 1), 'posted'))
        self.assertEqual(lease.outstanding_amount, 10677.02)
        # in order, and not paid from the bank
        with self.assertRaises(UserError):
            self._lines(lease)[2]._create_bill()
        with self.assertRaises(UserError):
            self._pay(self._lines(lease)[1])
        # the bill is paid like any vendor bill
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=bill.ids,
        ).create({'payment_date': date(2025, 2, 5)})._create_payments()
        self.assertIn(bill.payment_state, ('paid', 'in_payment'))
        self.assertEqual(line.bill_status, 'paid')
        # a paid bill is not cancelled from the lease
        with self.assertRaises(UserError):
            line.action_cancel_payment()

    def test_bill_taxes(self):
        """ The taxes of the lease go on the lines of the bill, the withholding tax on the interest only. """
        lease = self._create_lease(
            bill_tax_ids=[Command.set(self.vat_tax.ids)], withholding_tax_id=self.withholding_tax.id)
        line = self._lines(lease)[0]
        self.assertEqual((line.withholding, line.net_amount), (0.58, 999.42))
        bill = line._create_bill()
        vat = bill.line_ids.filtered(lambda aml: aml.tax_line_id == self.vat_tax)
        withholding = bill.line_ids.filtered(lambda aml: aml.tax_line_id == self.withholding_tax)
        self.assertEqual((vat.account_id, vat.debit), (self.vat_account, 70.0))
        self.assertEqual((withholding.account_id, withholding.credit), (self.withholding_account, 0.58))
        self.assertEqual(bill.amount_total, 1069.42)
        self.assertEqual(self._payment_term_line(bill).credit, 1069.42)
        interest_line = bill.invoice_line_ids.filtered(lambda aml: aml.account_id == self.interest_account)
        self.assertEqual(interest_line.tax_ids, self.vat_tax | self.withholding_tax)
        principal_line = bill.invoice_line_ids.filtered(lambda aml: aml.account_id == self.lease_long_term_account)
        self.assertEqual(principal_line.tax_ids, self.vat_tax)
        self.assertEqual(line.withholding, 0.58)

    def test_draft_bills(self):
        """ Bills left in draft: posted by hand, cancelled from the lease, posted before a reclassification. """
        lease = self._create_lease(bill_posting='draft')
        line = self._lines(lease)[0]
        bill = line._create_bill()
        self.assertEqual((bill.state, line.state, line.bill_status), ('draft', 'posted', 'draft'))
        with self.assertRaises(UserError):
            bill.button_cancel()
        with self.assertRaises(UserError):
            bill.unlink()
        with self.assertRaises(UserError):
            lease._reclassify(date(2025, 2, 28))
        line.action_cancel_payment()
        self.assertEqual((bill.state, line.state, line.bill_status), ('cancel', 'draft', 'to_bill'))
        self.assertFalse(line.move_id)
        bill = line._create_bill()
        bill.action_post()
        self.assertEqual(line.bill_status, 'posted')
        self.assertTrue(lease._reclassify(date(2025, 2, 28)))

    def test_cancel_posted_bill(self):
        """ The last bill is reversed by a credit note, its line is to bill again. """
        lease = self._create_lease()
        line = self._lines(lease)[0]
        bill = line._create_bill()
        line.action_cancel_payment()
        self.assertEqual(line.state, 'draft')
        self.assertEqual(bill.payment_state, 'reversed')
        refund = bill.reversal_move_ids
        self.assertEqual((refund.move_type, refund.loan_id, refund.loan_entry_type), ('in_refund', lease, 'bill'))
        self.assertEqual(lease.outstanding_amount, 11618.93)
        self.assertEqual(lease._account_balance_at(self.lease_long_term_account, date(2025, 3, 1)), 11618.93)

    def test_reclassification(self):
        """ The current part of the lease liability goes to the short-term account; the bills repay it. """
        lease = self._create_lease(payment_count=24, lease_payment=500.0)
        move = lease._reclassify(date(2025, 1, 31))
        within = round(sum(self._lines(lease)[:12].mapped('principal')), 2)
        self.assertEqual(self._entry(move), {
            self.lease_long_term_account.code: (within, 0.0, within),
            self.lease_short_term_account.code: (0.0, within, -within),
        })
        line = self._lines(lease)[0]
        bill = line._create_bill()
        principal_line = bill.invoice_line_ids.filtered(lambda aml: aml.account_id == self.lease_short_term_account)
        self.assertEqual(principal_line.debit, line.principal)

    def test_terms_locked(self):
        lease = self._create_lease()
        with self.assertRaises(UserError):
            lease.rate = 7.0
        with self.assertRaises(UserError):
            lease.lease_payment = 1200.0
        with self.assertRaises(UserError):
            self._draw(lease, date(2025, 1, 15), 100.0)
        with self.assertRaises(UserError):
            self._repay(lease, date(2025, 1, 15), 100.0)

    def test_configuration_required(self):
        lease = self._create_lease(confirm=False, account_rou_id=False)
        with self.assertRaises(UserError):
            lease.action_confirm()
        lease.account_rou_id = self.rou_account
        lease.bill_journal_id = False
        with self.assertRaises(UserError):
            lease.action_confirm()

    def test_cancel_recognition(self):
        """ The recognition is reversed like a drawdown, the lease can be recognized again. """
        lease = self._create_lease()
        operation = lease.operation_ids
        operation.action_cancel()
        self.assertEqual(operation.state, 'cancel')
        self.assertEqual(lease.outstanding_amount, 0.0)
        lease.action_recognize()
        self.assertEqual(lease.outstanding_amount, 11618.93)
        with self.assertRaises(UserError):
            lease.action_recognize()

    def test_cron_bills_due_payments(self):
        """ The scheduled action bills the lease payments due, in their order; the last one closes the lease. """
        lease = self._create_lease(bill_auto_create=True)
        manual = self._create_lease()
        self.env['account.loan.line']._cron_create_lease_bills()
        self.assertEqual(set(self._lines(lease).mapped('state')), {'posted'})
        self.assertEqual(len(lease.move_ids.filtered(lambda move: move.loan_entry_type == 'bill')), 12)
        self.assertEqual(lease.state, 'closed')
        self.assertEqual(lease.outstanding_amount, 0.0)
        self.assertEqual(set(self._lines(manual).mapped('state')), {'draft'})

    def test_create_bills_action(self):
        lease = self._create_lease()
        lines = self._lines(lease)[:3]
        action = lines[::-1].action_create_bills()
        self.assertEqual(set(lines.mapped('state')), {'posted'})
        self.assertEqual(len(self.env['account.move'].search(action['domain'])), 3)

    def test_report_types(self):
        """ The report lists the loans and the leases, or one type. """
        loan = self._create_loan()
        self._draw(loan)
        lease = self._create_lease()
        report = self.env['account.loan.report'].create({'date': date(2025, 1, 15)})
        report._compute_lines()
        self.assertEqual(report.line_ids.loan_id, loan | lease)
        self.assertEqual(report.line_ids.filtered(lambda line: line.loan_id == lease).loan_type, 'lease')
        report.loan_type = 'lease'
        report._compute_lines()
        self.assertEqual(report.line_ids.loan_id, lease)
        self.assertEqual(report.line_ids.outstanding, 11618.93)
        html = self.env['ir.actions.report']._render_qweb_html('om_account_loan.report_loan', lease.ids)[0]
        self.assertIn(b'Lessor', html)
