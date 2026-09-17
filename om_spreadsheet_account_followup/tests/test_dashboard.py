from odoo import Command, fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingHttpCommon
from odoo.addons.om_spreadsheet_account.tests.common import (
    built_dashboards, check_dashboards, check_sample, shipped_dashboard,
)


@tagged('post_install', '-at_install')
class TestDashboardFiles(TransactionCase):

    def test_files_are_built_from_the_script(self):
        """ The shipped file is the one the build script writes: run it after changing the dashboard. """
        for file_name, data in built_dashboards('om_spreadsheet_account_followup').items():
            with self.subTest(file=file_name):
                self.assertEqual(shipped_dashboard('om_spreadsheet_account_followup', file_name), data)

    def test_sample(self):
        check_sample(self, 'om_spreadsheet_account_followup.dashboard_followups_forecast')

    def test_dashboard_after_the_accounting_ones(self):
        dashboard = self.env.ref('om_spreadsheet_account_followup.dashboard_followups_forecast')
        self.assertEqual(dashboard.dashboard_group_id,
                         self.env.ref('spreadsheet_dashboard.spreadsheet_dashboard_group_finance'))
        self.assertGreater(dashboard.sequence,
                           self.env.ref('om_spreadsheet_account.dashboard_bank_cash').sequence)


@tagged('post_install', '-at_install')
class TestDashboardInBrowser(AccountTestInvoicingHttpCommon):

    def _accountant_admin(self):
        self.env.ref('base.user_admin').write({
            'company_id': self.env.company.id, 'company_ids': [Command.set(self.env.company.ids)],
            'group_ids': [Command.link(self.env.ref('account.group_account_user').id),
                          Command.link(self.env.ref('account.group_account_manager').id)],
        })

    def test_dashboard_computes_without_errors(self):
        self._accountant_admin()
        today = fields.Date.today()
        self.init_invoice('in_invoice', amounts=[300.0], taxes=[], invoice_date=today, post=True)
        self.init_invoice('out_invoice', amounts=[500.0], taxes=[], invoice_date=today, post=True)
        self.env['account.cash.forecast.item'].create({'name': 'Rent', 'amount': 800.0, 'recurrence': 'monthly'})
        # the invoice and the bill due today
        check_dashboards(self, ['Follow-ups and Cash Forecast'], expected={
            'Follow-ups and Cash Forecast': {'Data!B3': 500, 'Data!B4': 300},
        })
