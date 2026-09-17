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
        for file_name, data in built_dashboards('om_spreadsheet_account_budget').items():
            with self.subTest(file=file_name):
                self.assertEqual(shipped_dashboard('om_spreadsheet_account_budget', file_name), data)

    def test_sample(self):
        check_sample(self, 'om_spreadsheet_account_budget.dashboard_budgets')

    def test_dashboard_after_the_accounting_ones(self):
        dashboard = self.env.ref('om_spreadsheet_account_budget.dashboard_budgets')
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
        year_start, year_end = today.replace(month=1, day=1), today.replace(month=12, day=31)
        position = self.env['account.budget.position'].create({
            'name': 'Costs', 'budget_type': 'expense',
            'account_ids': [Command.set(self.company_data['default_account_expense'].ids)],
        })
        budget = self.env['account.budget'].create({
            'name': 'Budget', 'date_from': year_start, 'date_to': year_end,
            'line_ids': [Command.create({
                'name': 'Costs', 'position_id': position.id, 'planned_amount': 1000.0,
                'date_from': year_start, 'date_to': year_end,
            })],
        })
        budget.action_budget_confirm()
        budget.action_budget_validate()
        self.init_invoice('in_invoice', amounts=[300.0], taxes=[], invoice_date=today, post=True)
        # the planned expenses, and the actual ones: the bill booked on the account of the budget line
        check_dashboards(self, ['Budgets'], expected={'Budgets': {'Data!B1': 1000, 'Data!B3': 300}})
