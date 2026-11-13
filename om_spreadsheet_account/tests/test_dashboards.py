import json

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingHttpCommon
from .common import built_dashboards, check_dashboards, check_sample, shipped_dashboard

DASHBOARDS = {
    'om_spreadsheet_account.dashboard_accounting_overview': 'accounting_overview_dashboard.json',
    'om_spreadsheet_account.dashboard_profit_and_loss': 'profit_and_loss_dashboard.json',
    'om_spreadsheet_account.dashboard_balance_sheet': 'balance_sheet_dashboard.json',
    'om_spreadsheet_account.dashboard_receivables_payables': 'receivables_payables_dashboard.json',
    'om_spreadsheet_account.dashboard_bank_cash': 'bank_cash_dashboard.json',
}


@tagged('post_install', '-at_install')
class TestDashboardFiles(TransactionCase):

    def test_files_are_built_from_the_script(self):
        """ The shipped files are the ones the build script writes: run it after changing a dashboard. """
        built = built_dashboards('om_spreadsheet_account')
        self.assertEqual(set(built), set(DASHBOARDS.values()))
        for file_name, data in built.items():
            with self.subTest(file=file_name):
                self.assertEqual(shipped_dashboard('om_spreadsheet_account', file_name), data)

    def test_dashboards_in_the_finance_section(self):
        finance = self.env.ref('spreadsheet_dashboard.spreadsheet_dashboard_group_finance')
        for xmlid in DASHBOARDS:
            dashboard = self.env.ref(xmlid)
            with self.subTest(dashboard=dashboard.name):
                self.assertEqual(dashboard.dashboard_group_id, finance)
                self.assertTrue(dashboard.is_published)
                self.assertIn(self.env.ref('account.group_account_readonly'), dashboard.group_ids)
                self.assertTrue(json.loads(dashboard._get_serialized_readonly_dashboard())['snapshot']['sheets'])

    def test_samples(self):
        for xmlid in DASHBOARDS:
            with self.subTest(dashboard=xmlid):
                check_sample(self, xmlid)

    def test_billing_users_only_see_the_partner_dashboard(self):
        billing = self.env['res.users'].create({
            'name': 'Dashboard Billing', 'login': 'dashboard_billing',
            'group_ids': [(6, 0, [self.env.ref('account.group_account_invoice').id])],
        })
        visible = self.env['spreadsheet.dashboard'].with_user(billing).search([]).mapped('name')
        self.assertIn('Receivables and Payables', visible)
        self.assertNotIn('Balance Sheet', visible)


@tagged('post_install', '-at_install')
class TestDashboardsInBrowser(AccountTestInvoicingHttpCommon):

    def test_dashboards_compute_without_errors(self):
        self.env.ref('base.user_admin').write({
            'company_id': self.env.company.id, 'company_ids': [(6, 0, self.env.company.ids)],
            'group_ids': [(4, self.env.ref('account.group_account_user').id),
                          (4, self.env.ref('account.group_account_manager').id)],
        })
        today = fields.Date.today()
        self.init_invoice('out_invoice', amounts=[1000.0], taxes=[], invoice_date=today, post=True)
        self.init_invoice('in_invoice', amounts=[300.0], taxes=[], invoice_date=today, post=True)
        self.env['account.bank.statement.line'].create({
            'journal_id': self.company_data['default_journal_bank'].id, 'date': today, 'amount': 250.0,
            'payment_ref': 'Deposit',
        })
        check_dashboards(self, [
            'Accounting Overview', 'Profit and Loss', 'Balance Sheet', 'Receivables and Payables', 'Bank and Cash',
        ], expected={
            # revenue, expenses and net profit of the year to date, compared with last year
            'Accounting Overview': {'Data!B16': 1000, 'Data!B20': 300, 'Data!B21': 700, 'Data!C16': 0,
                                    'Data!B4': 'Same Period Last Year'},
            # the revenue of the period, and of the month of today
            'Profit and Loss': {'Dashboard!B18': 1000},
            # the invoice still owed and the bill still to pay at the end of the period
            'Balance Sheet': {'Dashboard!B11': 1000, 'Dashboard!B19': 300, 'Dashboard!B29': 700},
            # the balance of the bank, and the transaction to reconcile
            'Bank and Cash': {'Data!B1': 250, 'Data!B4': 1},
            # what the customer and the vendor owe, not due yet
            'Receivables and Payables': {'Data!B2': 1000, 'Data!C2': 300},
        })
