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
        for file_name, data in built_dashboards('om_spreadsheet_account_asset').items():
            with self.subTest(file=file_name):
                self.assertEqual(shipped_dashboard('om_spreadsheet_account_asset', file_name), data)

    def test_sample(self):
        check_sample(self, 'om_spreadsheet_account_asset.dashboard_assets')

    def test_dashboard_after_the_accounting_ones(self):
        dashboard = self.env.ref('om_spreadsheet_account_asset.dashboard_assets')
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
        year_start = fields.Date.today().replace(month=1, day=1)
        Account = self.env['account.account']
        category = self.env['account.asset.category'].create({
            'name': 'Computers',
            'journal_id': self.company_data['default_journal_misc'].id,
            'account_asset_id': Account.create({'code': 'DASHFA', 'name': 'Equipment',
                                                'account_type': 'asset_fixed'}).id,
            'account_depreciation_id': Account.create({'code': 'DASHAD', 'name': 'Accumulated Depreciation',
                                                       'account_type': 'asset_fixed'}).id,
            'account_depreciation_expense_id': Account.create({'code': 'DASHDE', 'name': 'Depreciation',
                                                               'account_type': 'expense_depreciation'}).id,
            'method_number': 12,
            'method_period': 1,
        })
        self.env['account.asset.asset'].create({
            'name': 'Laptop', 'category_id': category.id, 'value': 1200.0, 'date': year_start,
            'method_number': 12, 'method_period': 1,
        }).validate()
        # the gross value and the number of running assets
        check_dashboards(self, ['Assets'], expected={'Assets': {'Data!B1': 1200, 'Data!B6': 1}})
