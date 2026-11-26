from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

CAPITAL = 'Capital and Reserves'
PREVIOUS = 'Previous Years Unallocated Earnings'
CURRENT = 'Current Year Unallocated Earnings'


@tagged('post_install', '-at_install')
class TestUnallocatedEarnings(AccountTestInvoicingCommon):
    """ The earnings in the equity of the Balance Sheet, split by fiscal year.

    Odoo does not carry forward the balances of the income, the expense and the unaffected earnings
    account (include_initial_balance): they start again at zero every fiscal year. The closing of a year
    (the Close Fiscal Year wizard of om_fiscal_year) allocates its result to the reserves with an entry
    on the unaffected earnings account, a debit for a profit. Their balance is the earnings not allocated
    yet, of the previous fiscal years and of the current one. The profit of every year since the first
    entry, and the unaffected earnings account as a line of its own, would only make sense together.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.retained_earnings = cls.env['account.account'].create({
            'code': 'RETEARN', 'name': 'Retained Earnings', 'account_type': 'equity',
        })

    def _sale(self, date, amount):
        self.init_invoice('out_invoice', amounts=[amount], invoice_date=date, taxes=[], post=True)

    def _allocate(self, date, amount):
        """ The result of the year to the reserves, as the year-end closing does """
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': date,
            'line_ids': [
                (0, 0, {'name': 'allocation', 'balance': amount,
                        'account_id': self.env.company.get_unaffected_earnings_account().id}),
                (0, 0, {'name': 'allocation', 'balance': -amount, 'account_id': self.retained_earnings.id}),
            ],
        }).action_post()

    def _printed(self, date_to):
        """ :return: {name: amount} of the lines of the Balance Sheet, as printed """
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        context = {'date_from': False, 'date_to': date_to, 'state': 'posted', 'strict_range': False,
                   'company_id': self.env.company.id}
        lines = self.env['report.accounting_pdf_reports.report_financial'].with_context(**context).get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': context,
            'enable_filter': False,
            'debit_credit': False,
        })
        return {line['name']: line['balance'] for line in lines}

    def assertEquity(self, date_to, capital, previous, current):
        printed = self._printed(date_to)
        with self.subTest(date_to=date_to):
            self.assertAlmostEqual(printed[CAPITAL], capital, 2, CAPITAL)
            self.assertAlmostEqual(printed[PREVIOUS], previous, 2, PREVIOUS)
            self.assertAlmostEqual(printed[CURRENT], current, 2, CURRENT)
            self.assertAlmostEqual(printed['Equity'], capital + previous + current, 2)
            self.assertAlmostEqual(printed['Assets'], printed['Liabilities and Equity'], 2,
                                   'the two sides of the balance sheet face each other')
            unaffected = self.env.company.get_unaffected_earnings_account()
            self.assertFalse([name for name in printed if name.startswith(unaffected.code)],
                             'the unaffected earnings account is not a line of its own')

    def test_a_year_allocated_at_its_end(self):
        self._sale('2025-06-01', 1000.0)
        self._allocate('2025-12-31', 1000.0)
        self._sale('2026-03-01', 300.0)

        self.assertEquity('2026-06-30', capital=1000.0, previous=0.0, current=300.0)
        self.assertEquity('2025-12-31', capital=1000.0, previous=0.0, current=0.0)

    def test_a_year_not_allocated_yet(self):
        """ Before the allocation, the profit of last year is apart from the profit of this year """
        self._sale('2025-06-01', 1000.0)
        self._sale('2026-03-01', 300.0)

        self.assertEquity('2026-06-30', capital=0.0, previous=1000.0, current=300.0)
        self.assertEquity('2025-12-31', capital=0.0, previous=0.0, current=1000.0)

    def test_an_allocation_dated_after_the_year(self):
        """ Dated after the last day of the year it closes, as the Close Fiscal Year wizard dates it by default,
        the allocation lowers the earnings of the year after: the unallocated earnings still add up """
        self._sale('2025-06-01', 1000.0)
        self._allocate('2026-01-01', 1000.0)
        self._sale('2026-03-01', 300.0)

        self.assertEquity('2026-06-30', capital=1000.0, previous=1000.0, current=-700.0)

    def test_a_fiscal_year_that_is_not_the_calendar_year(self):
        self.env.company.write({'fiscalyear_last_month': '3', 'fiscalyear_last_day': 31})
        self._sale('2025-06-01', 1000.0)
        self._allocate('2026-03-31', 1000.0)
        self._sale('2026-05-01', 300.0)

        self.assertEquity('2026-03-31', capital=1000.0, previous=0.0, current=0.0)
        self.assertEquity('2026-06-30', capital=1000.0, previous=0.0, current=300.0)

    def test_an_earnings_section_of_ones_own(self):
        """ The type serves in a report of one's own, its sign as any section's """
        self._sale('2025-06-01', 1000.0)
        self._sale('2026-03-01', 300.0)
        report = self.env['account.financial.report'].create({'name': 'Earnings', 'type': 'sum'})
        self.env['account.financial.report'].create([
            {'name': 'Before', 'parent_id': report.id, 'type': 'earnings', 'earnings_period': 'previous',
             'sign': '-1'},
            {'name': 'This year', 'parent_id': report.id, 'type': 'earnings', 'earnings_period': 'current',
             'sign': '1'},
        ])
        context = {'date_to': '2026-06-30', 'state': 'posted', 'company_id': self.env.company.id}
        lines = {line['name']: line['balance'] for line in
                 self.env['report.accounting_pdf_reports.report_financial'].get_account_lines({
                     'account_report_id': (report.id, report.name), 'used_context': context,
                     'enable_filter': False, 'debit_credit': False})}
        self.assertAlmostEqual(lines['Before'], 1000.0, 2)
        self.assertAlmostEqual(lines['This year'], -300.0, 2, 'a credit, its sign preserved')
