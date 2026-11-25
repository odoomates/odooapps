from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from .common import build_script


@tagged('post_install', '-at_install')
class TestBalanceSheetDashboard(AccountTestInvoicingCommon):
    """ The equity of the Balance Sheet dashboard, its lines computed as the dashboard computes them: the
    OM.ACCOUNT.BALANCE of their account types at the date, from the start of the fiscal year for the earnings,
    and the sums of the lines above.

    The income, the expense and the unaffected earnings account start again at zero every fiscal year: the
    year's result is allocated to the reserves by an entry dated at its end that debits the unaffected earnings
    account (the year-end closing). Once a year is allocated, its profit is in the Capital and
    Reserves, and in neither of the earnings. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lines = build_script('om_spreadsheet_account').BALANCE_LINES
        cls.retained_earnings = cls.env['account.account'].create({
            'code': 'RETEARN', 'name': 'Retained Earnings', 'account_type': 'equity',
        })

    def _sale(self, date, amount):
        self.init_invoice('out_invoice', amounts=[amount], invoice_date=date, taxes=[], post=True)

    def _allocate(self, date, amount):
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': date,
            'line_ids': [
                (0, 0, {'name': 'allocation', 'balance': amount,
                        'account_id': self.env.company.get_unaffected_earnings_account().id}),
                (0, 0, {'name': 'allocation', 'balance': -amount, 'account_id': self.retained_earnings.id}),
            ],
        }).action_post()

    def _dashboard(self, date_to):
        """ :return: {line key: amount} of the Balance Sheet dashboard at ``date_to`` """
        fiscal_start = self.env.company.compute_fiscalyear_dates(fields.Date.to_date(date_to))['date_from']

        def balance(account_types, date_from):
            return self.env['account.move.line'].om_spreadsheet_fetch_balance([{
                'account_types': list(account_types), 'date_from': date_from and str(date_from),
                'date_to': date_to}])[0]['balance']

        amounts = {}
        for key, _text, members, sign, kind in self.lines:
            if kind == 'line':
                amounts[key] = sign * balance(members, False)
            elif kind == 'earnings':
                amounts[key] = sign * balance(members, fiscal_start)
            elif kind != 'title':
                amounts[key] = sum(-amounts[member[1:]] if member.startswith('-') else amounts[member]
                                   for member in members)
        return amounts

    def assertEquity(self, date_to, capital, current, previous):
        amounts = self._dashboard(date_to)
        with self.subTest(date_to=date_to):
            self.assertAlmostEqual(amounts['capital'], capital, 2, 'Capital and Reserves')
            self.assertAlmostEqual(amounts['current_earnings'], current, 2, 'Current Year Earnings')
            self.assertAlmostEqual(amounts['previous_earnings'], previous, 2, 'Previous Years Unallocated Earnings')
            self.assertAlmostEqual(amounts['total_equity'], amounts['total_assets'] - amounts['total_liabilities'], 2)

    def test_a_year_allocated_at_its_end(self):
        self._sale('2025-06-01', 1000.0)
        self._allocate('2025-12-31', 1000.0)
        self._sale('2026-03-01', 300.0)

        self.assertEquity('2026-06-30', capital=1000.0, current=300.0, previous=0.0)
        self.assertEquity('2025-12-31', capital=1000.0, current=0.0, previous=0.0)

    def test_a_year_not_allocated_yet(self):
        self._sale('2025-06-01', 1000.0)
        self._sale('2026-03-01', 300.0)

        self.assertEquity('2026-06-30', capital=0.0, current=300.0, previous=1000.0)
        self.assertEquity('2025-12-31', capital=0.0, current=1000.0, previous=0.0)
