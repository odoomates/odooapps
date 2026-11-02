from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestWithholding(LoanCommon):

    def test_withholding_on_schedule(self):
        """ The schedule shows the tax withheld on the interest of each line and what the lender receives. """
        loan = self._create_loan(withholding_tax_id=self.withholding_tax.id)
        lines = self._lines(loan)
        self.assertEqual((lines[0].interest, lines[0].withholding, lines[0].net_amount), (500.0, 5.0, 8601.64))
        self.assertEqual(loan.withholding_total, round(sum(lines.mapped('withholding')), 2))
        loan.withholding_tax_id = False
        self.assertEqual(lines[0].withholding, 0.0)

    def test_payment_withholds_tax(self):
        """ Dr loan + Dr interest / Cr withholding tax (on its account, as a tax line) + Cr outstanding payments
        for the instalment less the tax. """
        loan = self._create_loan(withholding_tax_id=self.withholding_tax.id)
        self._draw(loan)
        line = self._lines(loan)[0]
        move = self._pay(line)
        self.assertEqual(self._entry(move), {
            self.long_term_account.code: (8106.64, 0.0, 8106.64),
            self.interest_account.code: (500.0, 0.0, 500.0),
            self.withholding_account.code: (0.0, 5.0, -5.0),
            self.outstanding_payments.code: (0.0, 8601.64, -8601.64),
        })
        tax_line = move.line_ids.filtered(lambda aml: aml.account_id == self.withholding_account)
        self.assertEqual(tax_line.tax_line_id, self.withholding_tax)
        self.assertEqual(tax_line.tax_base_amount, 500.0)
        self.assertEqual(line.withholding, 5.0)
        # what was withheld stays on the paid line
        loan.withholding_tax_id = False
        self.assertEqual(line.withholding, 5.0)

    def test_withholding_changed_in_wizard(self):
        """ The tax withheld by the bank, if it differs, is set when paying. """
        loan = self._create_loan(withholding_tax_id=self.withholding_tax.id)
        self._draw(loan)
        line = self._lines(loan)[0]
        wizard = self.env['account.loan.pay'].create({'line_id': line.id})
        self.assertEqual((wizard.withholding, wizard.net_amount), (5.0, 8601.64))
        wizard.interest = 510.0
        self.assertEqual(wizard.withholding, 5.1)
        wizard.withholding = 5.0
        wizard.action_confirm()
        self.assertEqual(self._entry(line.move_id)[self.withholding_account.code], (0.0, 5.0, -5.0))
        self.assertEqual(line.withholding, 5.0)
        wizard = self.env['account.loan.pay'].create({'line_id': self._lines(loan)[1].id})
        wizard.withholding = 1000.0
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_cancel_payment_with_withholding(self):
        loan = self._create_loan(withholding_tax_id=self.withholding_tax.id)
        self._draw(loan)
        line = self._lines(loan)[0]
        move = self._pay(line)
        line.action_cancel_payment()
        self.assertEqual(move.reversal_move_ids.line_ids.filtered(
            lambda aml: aml.account_id == self.withholding_account).debit, 5.0)
        self.assertEqual(line.withholding, 5.0)

    def test_early_repayment_withholds_tax(self):
        """ The interest of an early repayment has its tax withheld too. """
        loan = self._create_loan(withholding_tax_id=self.withholding_tax.id)
        self._draw(loan)
        operation = self._repay(loan, date(2025, 1, 16), 100000.0, interest=250.0)
        self.assertEqual(operation.withholding, 2.5)
        entry = self._entry(operation.move_id)
        self.assertEqual(entry[self.withholding_account.code], (0.0, 2.5, -2.5))
        self.assertEqual(entry[self.outstanding_payments.code], (0.0, 100247.5, -100247.5))
        report = self.env['account.loan.report'].create({'date': date(2025, 1, 31)})
        report._compute_lines()
        self.assertEqual(report.line_ids.filtered(lambda line: line.loan_id == loan).withheld, 2.5)

    def test_withholding_tax_negative(self):
        """ A withholding tax reduces the payment: its amount is negative. """
        positive = self._create_withholding_tax(1.0, name='Positive tax')
        with self.assertRaises(ValidationError):
            self._create_loan(confirm=False, withholding_tax_id=positive.id)

    def test_withholding_without_account(self):
        tax = self._create_withholding_tax(-1.0, name='WHT without account')
        tax.invoice_repartition_line_ids.filtered(lambda rep: rep.repartition_type == 'tax').account_id = False
        loan = self._create_loan(withholding_tax_id=tax.id)
        self._draw(loan)
        with self.assertRaises(UserError):
            self._pay(self._lines(loan)[0])

    def test_pdf_shows_withholding(self):
        loan = self._create_loan(withholding_tax_id=self.withholding_tax.id)
        html = self.env['ir.actions.report']._render_qweb_html('om_account_loan.report_loan', loan.ids)[0]
        self.assertIn(b'Withholding Tax', html)
        self.assertIn(b'Net Payment', html)
