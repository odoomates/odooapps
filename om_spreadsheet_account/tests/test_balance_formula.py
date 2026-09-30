from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBalanceFormula(AccountTestInvoicingCommon):
    """ The server side of the OM.ACCOUNT.BALANCE formula of the statement dashboards. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_company_data = cls.setup_other_company()
        cls.company = cls.company_data['company']
        cls.other_company = cls.other_company_data['company']
        cls.env.user.company_ids = [Command.link(cls.other_company.id)]

    def _fetch(self, companies, *args_list):
        lines = self.env['account.move.line'].with_context(allowed_company_ids=companies.ids)
        return [result['balance'] for result in lines.om_spreadsheet_fetch_balance(list(args_list))]

    def _args(self, account_types, date_from=False, date_to=False, include_unposted=False):
        return {'account_types': account_types, 'date_from': date_from, 'date_to': date_to,
                'include_unposted': include_unposted}

    def _invoice(self, amount, date, company=None, post=True):
        return self.init_invoice('out_invoice', amounts=[amount], taxes=[], invoice_date=date, post=post,
                                 company=company)

    def test_periods_and_types(self):
        self._invoice(1000.0, '2025-03-10')
        self._invoice(400.0, '2025-05-20')
        self._invoice(50.0, '2024-12-31')
        income, receivable = self._fetch(
            self.company,
            self._args(['income'], '2025-01-01', '2025-12-31'),
            self._args(['asset_receivable'], False, '2025-03-31'),
        )
        self.assertAlmostEqual(income, -1400.0, msg='the income of the period only')
        self.assertAlmostEqual(receivable, 1050.0, msg='without a start, everything up to the end')
        both, = self._fetch(self.company, self._args(['income', 'asset_receivable'], '2025-05-01', '2025-05-31'))
        self.assertAlmostEqual(both, 0.0, msg='the types are added up')

    def test_selected_companies(self):
        self._invoice(1000.0, '2025-03-10')
        self._invoice(300.0, '2025-03-10', company=self.other_company)
        period = self._args(['income'], '2025-01-01', '2025-12-31')
        self.assertAlmostEqual(self._fetch(self.company, period)[0], -1000.0)
        self.assertAlmostEqual(self._fetch(self.other_company, period)[0], -300.0)
        self.assertAlmostEqual(self._fetch(self.company | self.other_company, period)[0], -1300.0,
                               msg='the companies selected in the switcher are added up')

    def test_unposted_entries(self):
        self._invoice(1000.0, '2025-03-10', post=False)
        self._invoice(200.0, '2025-03-10').button_cancel()
        posted, all_entries = self._fetch(
            self.company,
            self._args(['income'], '2025-01-01', '2025-12-31'),
            self._args(['income'], '2025-01-01', '2025-12-31', include_unposted=True),
        )
        self.assertAlmostEqual(posted, 0.0)
        self.assertAlmostEqual(all_entries, -1000.0, msg='the drafts, never the cancelled entries')
