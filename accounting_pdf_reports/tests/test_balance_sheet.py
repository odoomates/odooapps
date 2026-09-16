from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBalanceSheet(AccountTestInvoicingCommon):

    def _balance_sheet(self, date_to):
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        balances = self.env['report.accounting_pdf_reports.report_financial'].with_context(
            date_from=False, date_to=date_to, state='posted', strict_range=False,
            company_id=self.env.company.id,
        )._compute_report_balance(report.children_ids)
        return {line.name: balances[line.id]['balance'] for line in report.children_ids}

    def test_balance_sheet_balances_with_current_year_earnings_postings(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-06-01', taxes=[], post=True)
        retained_earnings = self.env['account.account'].create({
            'code': 'RETEARN', 'name': 'Retained Earnings', 'account_type': 'equity',
        })
        # e.g. the transfer of the earnings of 2025, or an opening balance difference
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2026-01-01',
            'line_ids': [
                (0, 0, {'name': 'transfer', 'balance': 1000.0,
                        'account_id': self.env.company.get_unaffected_earnings_account().id}),
                (0, 0, {'name': 'transfer', 'balance': -1000.0, 'account_id': retained_earnings.id}),
            ],
        }).action_post()

        for date_to in ('2025-12-31', '2026-12-31'):
            with self.subTest(date_to=date_to):
                lines = self._balance_sheet(date_to)
                self.assertAlmostEqual(sum(lines.values()), 0.0)
                self.assertAlmostEqual(lines['Assets'], 1000.0)

    def test_prepayments_are_assets(self):
        prepayments = self.env['account.account'].create({
            'code': 'PREPAID', 'name': 'Prepaid Rent', 'account_type': 'asset_prepayments',
        })
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2025-06-01',
            'line_ids': [
                (0, 0, {'name': 'rent', 'balance': 600.0, 'account_id': prepayments.id}),
                (0, 0, {'name': 'rent', 'balance': -600.0, 'account_id': self.company_data['default_account_payable'].id}),
            ],
        }).action_post()
        lines = self._balance_sheet('2025-12-31')
        self.assertAlmostEqual(lines['Assets'], 600.0)
        self.assertAlmostEqual(sum(lines.values()), 0.0)
