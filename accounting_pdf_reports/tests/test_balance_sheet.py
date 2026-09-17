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

    def _printed(self, date_to):
        """ :return: {name: amount} as the report prints them, the sign of each line applied """
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        lines = self.env['report.accounting_pdf_reports.report_financial'].with_context(
            date_from=False, date_to=date_to, state='posted', strict_range=False,
            company_id=self.env.company.id,
        ).get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': {'date_from': False, 'date_to': date_to, 'state': 'posted',
                             'strict_range': False, 'company_id': self.env.company.id},
            'enable_filter': False,
            'debit_credit': False,
        })
        return {line['name']: line['balance'] for line in lines if line.get('type') == 'report'}

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
                (0, 0, {'name': 'rent', 'balance': -600.0,
                        'account_id': self.company_data['default_account_payable'].id}),
            ],
        }).action_post()
        lines = self._balance_sheet('2025-12-31')
        self.assertAlmostEqual(lines['Assets'], 600.0)
        self.assertAlmostEqual(sum(lines.values()), 0.0)

    def test_the_sections_are_named_apart(self):
        """ Up to 1.x a Liability sat inside a Liability, and the equity was counted among the liabilities. """
        names = [line.name for line in self.env.ref(
            'accounting_pdf_reports.account_financial_report_balancesheet0').children_ids]
        self.assertEqual(names, ['Assets', 'Liabilities and Equity'])
        sections = [line.name for line in self.env.ref(
            'accounting_pdf_reports.account_financial_report_liabilitysum0').children_ids]
        self.assertEqual(sections, ['Liabilities', 'Equity'])
        equity = [line.name for line in self.env.ref(
            'accounting_pdf_reports.account_financial_report_equity0').children_ids]
        self.assertEqual(equity, ['Capital and Reserves', 'Profit (Loss) to report'],
                         'the profit of the period belongs to the owners')

    def test_the_equity_is_not_among_the_liabilities(self):
        equity_types = self.env.ref('accounting_pdf_reports.account_financial_report_equity_accounts0')\
            .account_type_ids.mapped('type')
        liability_types = self.env.ref('accounting_pdf_reports.account_financial_report_liability0')\
            .account_type_ids.mapped('type')
        self.assertEqual(set(equity_types), {'equity', 'equity_unaffected'})
        self.assertFalse(set(equity_types) & set(liability_types), 'nothing is counted on both sides')
        self.assertIn('liability_credit_card', liability_types,
                      'a credit card is money owed: without it the balance sheet does not balance')

    def test_what_is_owed_prints_positive(self):
        """ A balance sheet is read with the liabilities and the equity positive, facing the assets. """
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-06-01', taxes=[], post=True)
        printed = self._printed('2025-12-31')
        self.assertGreater(printed['Assets'], 0.0)
        self.assertGreater(printed['Liabilities and Equity'], 0.0,
                           'what the company owes and what belongs to its owners, printed positive')
        self.assertAlmostEqual(printed['Assets'], printed['Liabilities and Equity'],
                               msg='the two sides of the balance sheet face each other')
        self.assertAlmostEqual(printed['Equity'], 1000.0, msg='the profit of the period is in the equity')
        self.assertAlmostEqual(printed['Profit (Loss) to report'], 1000.0)
        self.assertAlmostEqual(printed['Capital and Reserves'], 0.0)

    def test_a_credit_card_balances(self):
        """ The credit card accounts belong to the liabilities: the report balances with one in use. """
        credit_card = self.env['account.account'].create({
            'code': 'CCARD', 'name': 'Company Card', 'account_type': 'liability_credit_card',
        })
        expense = self.env['account.account'].create({
            'code': 'CCEXP', 'name': 'Card Expense', 'account_type': 'expense',
        })
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2025-06-01',
            'line_ids': [
                (0, 0, {'name': 'card', 'balance': 250.0, 'account_id': expense.id}),
                (0, 0, {'name': 'card', 'balance': -250.0, 'account_id': credit_card.id}),
            ],
        }).action_post()
        lines = self._balance_sheet('2025-12-31')
        self.assertAlmostEqual(sum(lines.values()), 0.0)

    def test_the_lines_carry_their_level(self):
        """ The sections are indented by their depth in the report, the title of the report is not printed. """
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        lines = self.env['report.accounting_pdf_reports.report_financial'].get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': {'state': 'posted', 'company_id': self.env.company.id},
            'enable_filter': False,
            'debit_credit': False,
        })
        levels = {line['name']: line['level'] for line in lines if line['type'] == 'report'}
        self.assertEqual(levels, {
            'Balance Sheet': 0,
            'Assets': 1,
            'Liabilities and Equity': 1,
            'Liabilities': 2,
            'Equity': 2,
            'Capital and Reserves': 3,
            'Profit (Loss) to report': 3,
        })
        self.env.ref('accounting_pdf_reports.account_financial_report_equity0').style_overwrite = '1'
        lines = self.env['report.accounting_pdf_reports.report_financial'].get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': {'state': 'posted', 'company_id': self.env.company.id},
            'enable_filter': False,
            'debit_credit': False,
        })
        self.assertEqual(next(line['level'] for line in lines if line['name'] == 'Equity'), 1,
                         'a style chosen on the line wins over its depth')
