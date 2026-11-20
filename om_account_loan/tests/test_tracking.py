from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.tests import new_test_user, tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanTracking(LoanCommon):

    def _bodies(self, loan):
        return ' | '.join(loan.message_ids.mapped(lambda message: str(message.body)))

    def test_chatter(self):
        """ The payments, the reclassifications, the rate changes and the lines changed by hand are in the
        chatter of the loan. """
        loan = self._create_loan(rate_type='floating', payment_count=24)
        self._draw(loan)
        lines = self._lines(loan)
        self._pay(lines[0])
        self.assertIn('Instalment 1 paid on', self._bodies(loan))
        loan._reclassify(date(2025, 2, 28))
        self.assertIn('moved to the short-term account', self._bodies(loan))
        loan.rate_line_ids = [Command.create({'date': date(2025, 3, 2), 'rate': 7.5})]
        self.assertIn('Rate change: 7.5 % from', self._bodies(loan))
        lines[2].principal = 100.0
        self.assertIn('Instalment 3 changed: Principal', self._bodies(loan))

    def test_lease_bill_in_chatter(self):
        lease = self._create_lease()
        bill = self._lines(lease)[0]._create_bill()
        self.assertIn(f'Bill {bill.display_name} of the lease payment 1 created', self._bodies(lease))

    def test_invoicing_user_reverses_reclassification(self):
        """ The reclassification is not a schedule entry: an invoicing user may reverse it, and the reversal
        stays in the balances of the loan. """
        invoicing = new_test_user(
            self.env, login='loan_track_invoicing', groups='account.group_account_invoice',
            company_id=self.env.company.id)
        loan = self._create_loan(payment_count=24)
        self._draw(loan)
        move = loan._reclassify(date(2025, 1, 31))
        reversal = move.with_user(invoicing)._reverse_moves([{'date': move.date}], cancel=True)
        self.assertEqual(reversal.sudo().loan_id, loan)
        self.assertEqual(loan._account_balance_at(self.short_term_account, date(2025, 1, 31)), 0.0)

    def test_report_totals_in_company_currency(self):
        """ The loans in several currencies add up in the company currency only. """
        eur = self.setup_other_currency('EUR', rates=[('2025-01-01', 2.0)])
        loan = self._create_loan(payment_count=24)
        self._draw(loan)
        euro_loan = self._create_loan(currency_id=eur.id, payment_count=24)
        self._draw(euro_loan)
        report = self.env['account.loan.report'].create({'date': date(2025, 1, 31)})
        report._compute_lines()
        Line = self.env['account.loan.report.line']
        self.assertFalse(Line._fields['outstanding'].aggregator)
        euro_line = report.line_ids.filtered(lambda line: line.loan_id == euro_loan)
        self.assertEqual(euro_line.outstanding_company, 50000.0)
        self.assertEqual(euro_line.due_within_company + euro_line.due_after_company, 50000.0)
        self.assertAlmostEqual(euro_line.due_within_company, euro_line.due_within / 2, delta=0.01)
        self.assertEqual(sum(report.line_ids.mapped('outstanding_company')), 150000.0)

    def test_bill_left_draft_for_its_document_number(self):
        """ A journal using documents (Latin America) asks for the number of the lessor's document: the bill is
        left in draft, the lease says why. """
        lease = self._create_lease()
        with patch.object(type(self.env['account.move']), '_loan_needs_document_number', return_value=True):
            bill = self._lines(lease)[0]._create_bill()
        self.assertEqual(bill.state, 'draft')
        self.assertIn('asks for the document number', self._bodies(lease))
        bill.action_post()
        self.assertEqual(bill.state, 'posted')

    def test_lease_tax_withheld_on_payment(self):
        """ A tax withheld on the payments of the bills is not withheld by the schedule of the lease. """
        with patch.object(type(self.env['account.loan']), '_withholding_on_bill_payment', return_value=True):
            lease = self._create_lease(withholding_tax_id=self.withholding_tax.id)
            self.assertFalse(any(self._lines(lease).mapped('withholding')))
