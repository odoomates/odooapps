from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged

# where each menu of the accounting apps stands: daily work, reports, settings
PARENTS = {
    'om_recurring_payments.menu_recurring_payment': 'account.menu_finance_entries',
    'om_recurring_payments.menu_move_auto_post': 'account.menu_finance_entries',
    'om_fiscal_year.menu_action_change_lock_date': 'account.account_closing_menu',
    'om_fiscal_year.menu_fiscal_year_closing': 'account.account_closing_menu',
    'accounting_pdf_reports.menu_account_report_bs': 'account.account_reports_legal_statements_menu',
    'accounting_pdf_reports.menu_account_report_pl': 'account.account_reports_legal_statements_menu',
    'accounting_pdf_reports.menu_account_report_cash_flow': 'account.account_reports_legal_statements_menu',
    'accounting_pdf_reports.menu_account_report_annual': 'account.account_reports_legal_statements_menu',
    'accounting_pdf_reports.menu_partner_ledger': 'account.account_reports_partners_reports_menu',
    'accounting_pdf_reports.menu_aged_trial_balance': 'account.account_reports_partners_reports_menu',
    'accounting_pdf_reports.menu_account_report': 'account.account_reports_taxes_and_fiscal_menu',
    'accounting_pdf_reports.menu_account_reports': 'account.account_account_menu',
    'om_account_asset.menu_action_account_asset_asset_list_normal_purchase':
        'om_account_accountant.menu_account_management_config',
    'om_account_budget.menu_budget_post_form': 'om_account_accountant.menu_account_management_config',
    'om_recurring_payments.menu_recurring_template': 'om_account_accountant.menu_account_management_config',
    'om_fiscal_year.menu_account_period_closing_task': 'om_account_accountant.menu_account_management_config',
    'om_account_accountant.menu_review_journal_audit': 'account.account_audit_menu',
    'om_account_accountant.menu_review_moves_to_review': 'account.account_audit_control_menu',
    'om_account_accountant.menu_review_moves_unposted': 'account.account_audit_control_menu',
}
# the folders emptied by the arrangement: kept for the modules that put their own menus in them
EMPTIED = (
    'accounting_pdf_reports.menu_finance_legal_statement',
    'accounting_pdf_reports.menu_finance_partner_reports',
    'accounting_pdf_reports.menu_finance_reports_settings',
    'om_recurring_payments.menu_recurring_payments',
    'om_account_accountant.menu_account_templates',
)


@tagged('post_install', '-at_install')
class TestMenus(TransactionCase):

    def test_menus_are_arranged(self):
        for xmlid, parent in PARENTS.items():
            with self.subTest(menu=xmlid):
                self.assertEqual(self.env.ref(xmlid).parent_id, self.env.ref(parent))

    def test_the_emptied_folders_are_not_shown(self):
        admin = new_test_user(
            self.env, login='menu_admin', groups='base.group_system,base.group_no_one,account.group_account_manager',
            company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        visible = self.env['ir.ui.menu'].with_user(admin)._visible_menu_ids()
        for xmlid in EMPTIED:
            with self.subTest(menu=xmlid):
                menu = self.env.ref(xmlid)
                self.assertFalse(menu.child_id, xmlid)
                self.assertNotIn(menu.id, visible, xmlid)

    def test_accountant_sees_the_daily_work(self):
        accountant = new_test_user(
            self.env, login='menu_accountant', groups='account.group_account_user',
            company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        visible = self.env['ir.ui.menu'].with_user(accountant)._visible_menu_ids()
        for xmlid in ('om_recurring_payments.menu_recurring_payment',
                      'om_recurring_payments.menu_move_auto_post',
                      'accounting_pdf_reports.menu_action_account_moves_ledger_general',
                      'accounting_pdf_reports.menu_account_report_bs',
                      'accounting_pdf_reports.menu_account_report',
                      'om_account_accountant.menu_review_journal_audit',
                      'om_account_accountant.menu_review_moves_to_review',
                      'om_account_accountant.menu_review_moves_unposted'):
            self.assertIn(self.env.ref(xmlid).id, visible, xmlid)

    def test_the_review_actions_filter_on_the_core_filters(self):
        for xmlid, search_filter in (('om_account_accountant.action_moves_to_review', 'to_check'),
                                     ('om_account_accountant.action_moves_unposted', 'unposted')):
            with self.subTest(action=xmlid):
                action = self.env.ref(xmlid)
                self.assertIn(f"'search_default_{search_filter}': 1", action.context)
                search_view = self.env['account.move'].get_view(action.search_view_id.id, view_type='search')['arch']
                self.assertIn(f'name="{search_filter}"', search_view)
