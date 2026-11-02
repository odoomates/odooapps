from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestGeneralLedgerInitialBalance(AccountTestInvoicingCommon):

    def _company_accounts(self):
        """ The other company of the tests has the same codes, and the field of the company depends on the version """
        field = 'company_ids' if 'company_ids' in self.env['account.account']._fields else 'company_id'
        return self.env['account.account'].search([]).filtered(lambda account: self.env.company in account[field])

    def _ledger(self, **vals):
        wizard = self.env['account.report.general.ledger'].create(dict({
            'target_move': 'posted',
            'journal_ids': [Command.set(self.env['account.journal'].search([]).ids)],
        }, **vals))
        context = dict(active_model='account.account', active_ids=self._company_accounts().ids)
        action = wizard.with_context(**context).check_report()
        context.update(action.get('context') or {})
        values = self.env['report.' + action['report_name']].with_context(**context)._get_report_values(
            context.get('active_ids'), action['data'])
        return {account['code']: account for account in values['Accounts']}

    def _invoice(self, amount, day):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[amount], taxes=[], invoice_date=day, post=True)

    def setUp(self):
        super().setUp()
        self.env.company.fiscalyear_last_month = '12'
        self.env.company.fiscalyear_last_day = 31
        self.receivable = self.company_data['default_account_receivable'].code
        self.revenue = self.company_data['default_account_revenue'].code
        for amount, day in ((100.0, '2024-06-01'), (40.0, '2025-03-01'), (30.0, '2025-08-01')):
            self._invoice(amount, day)

    def test_income_starts_again_every_fiscal_year(self):
        ledger = self._ledger(date_from='2025-07-01', date_to='2025-12-31', display_account='all')
        # a balance sheet account carries its whole history
        self.assertEqual(ledger[self.receivable]['move_lines'][0]['lname'], 'Initial Balance')
        self.assertEqual(ledger[self.receivable]['move_lines'][0]['balance'], 140.0)
        self.assertEqual(ledger[self.receivable]['balance'], 170.0)
        # an income account only the current fiscal year
        self.assertEqual(ledger[self.revenue]['move_lines'][0]['balance'], -40.0)
        self.assertEqual(ledger[self.revenue]['balance'], -70.0)
        # the years before have a line of their own
        self.assertEqual(ledger['']['name'], 'Result Brought Forward')
        self.assertEqual(ledger['']['balance'], -100.0)
        self.assertEqual(ledger['']['credit'], 100.0)
        self.assertAlmostEqual(sum(account['balance'] for account in ledger.values()), 0.0)

    def test_first_day_of_the_fiscal_year(self):
        ledger = self._ledger(date_from='2025-01-01', date_to='2025-12-31', display_account='all')
        self.assertNotEqual(ledger[self.revenue]['move_lines'][0]['lname'], 'Initial Balance')
        self.assertEqual(ledger[self.revenue]['balance'], -70.0)
        self.assertEqual(ledger['']['balance'], -100.0)

    def test_fiscal_year_of_the_company(self):
        self.env.company.fiscalyear_last_month = '3'
        ledger = self._ledger(date_from='2025-07-01', date_to='2025-12-31', display_account='all')
        # the year starts in April 2025: 40.00 of March 2025 and 100.00 of 2024 are the years before
        self.assertEqual(ledger[self.revenue]['balance'], -30.0)
        self.assertEqual(ledger['']['balance'], -140.0)

    def test_no_line_when_nothing_is_brought_forward(self):
        ledger = self._ledger(date_from='2024-01-01', date_to='2024-12-31', display_account='all')
        self.assertNotIn('', ledger)

    def test_without_the_option(self):
        ledger = self._ledger(date_from='2025-07-01', date_to='2025-12-31', display_account='all',
                              initial_balance=False)
        self.assertEqual(ledger[self.revenue]['balance'], -30.0)
        self.assertNotIn('', ledger)

    def test_without_a_start_date(self):
        """ The default option needs no start date: the report covers the whole history, counted once. """
        ledger = self._ledger(date_from=False, date_to='2025-12-31', display_account='all')
        self.assertEqual(ledger[self.receivable]['balance'], 170.0)
        self.assertEqual(ledger[self.revenue]['balance'], -170.0)
        self.assertNotIn('', ledger)

    def test_same_figures_as_the_trial_balance(self):
        accounts = self._company_accounts()
        wizard = self.env['account.balance.report'].create({
            'target_move': 'posted', 'date_from': '2025-07-01', 'date_to': '2025-12-31', 'display_account': 'all',
            'journal_ids': [Command.set(self.env['account.journal'].search([]).ids)],
        })
        data = wizard.with_context(active_model='account.account', active_ids=accounts.ids).check_report()['data']
        lines = self.env['report.accounting_pdf_reports.report_trialbalance'].with_context(
            active_model='account.account', active_ids=accounts.ids)._get_report_values(accounts.ids, data)['Accounts']
        ledger = self._ledger(date_from='2025-07-01', date_to='2025-12-31', display_account='all')
        for line in lines:
            self.assertAlmostEqual(line['balance'], ledger[line['code']]['balance'], msg=line['code'])
