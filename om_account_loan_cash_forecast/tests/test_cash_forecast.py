from datetime import date

from odoo import Command
from odoo.tests import tagged

from odoo.addons.om_account_loan.tests.common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanCashForecast(LoanCommon):

    def _forecast(self):
        wizard = self.env['account.cash.forecast.report'].create({
            'date_from': date(2025, 1, 1), 'period_type': 'month', 'period_count': 4, 'overdue': 'exclude'})
        forecast = self.env['report.om_account_cash_forecast.report_cash_forecast']._get_forecast(wizard)
        return {row['key']: row['amounts'] for section in forecast['sections'] for row in section['rows']}

    def test_instalments_expected(self):
        """ The unpaid instalments are payments of the forecast on their due dates, net of the tax withheld. """
        loan = self._create_loan(withholding_tax_id=self.withholding_tax.id)
        self._draw(loan)
        lines = self._lines(loan)
        self._pay(lines[0])
        rows = self._forecast()
        # January, February (paid), March, April
        self.assertEqual(rows['loans_out'], [0.0, 0.0, -lines[1].net_amount, -lines[2].net_amount])

    def test_lease_payments_not_billed(self):
        """ The lease payments not billed yet are expected with the taxes of their bills; a bill created is a
        vendor bill of the forecast. """
        lease = self._create_lease(bill_tax_ids=[Command.set(self.vat_tax.ids)])
        lines = self._lines(lease)
        lines[0]._create_bill()
        rows = self._forecast()
        report = self.env['report.om_account_cash_forecast.report_cash_forecast']
        expected = [-report._lease_payment_with_taxes(line) for line in lines[1:3]]
        self.assertEqual(rows['leases_out'], [0.0, 0.0, *expected])
        self.assertAlmostEqual(expected[0], -1070.0, places=2)
        self.assertNotIn('loans_out', rows)

    def test_draft_loans_left_out(self):
        self._create_loan(confirm=False)
        self.assertNotIn('loans_out', self._forecast())
