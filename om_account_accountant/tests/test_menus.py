from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged

# where each menu of the accounting apps stands: daily work, reports, settings
PARENTS = {
    'om_account_reconcile.menu_bank_reconciliation': 'om_account_reconcile.menu_reconciliation',
    'om_account_reconcile.menu_open_items_reconciliation': 'om_account_reconcile.menu_reconciliation',
    'om_account_reconcile.menu_move_line_match': 'om_account_reconcile.menu_reconciliation',
    'om_account_reconcile.menu_reconciliation': 'account.menu_finance_entries',
    'om_account_asset.menu_action_account_asset_asset_form': 'account.menu_finance_entries',
    'om_account_budget.menu_account_budget': 'account.menu_finance_entries',
    'om_recurring_payments.menu_recurring_payment': 'account.menu_finance_entries',
    'om_account_cash_forecast.menu_cash_forecast_item': 'account.menu_finance_entries',
    'om_fiscal_year.menu_action_change_lock_date': 'account.account_closing_menu',
    'accounting_pdf_reports.menu_account_report_bs': 'account.account_reports_legal_statements_menu',
    'accounting_pdf_reports.menu_account_report_pl': 'account.account_reports_legal_statements_menu',
    'accounting_pdf_reports.menu_account_report_cash_flow': 'account.account_reports_legal_statements_menu',
    'accounting_pdf_reports.menu_partner_ledger': 'account.account_reports_partners_reports_menu',
    'accounting_pdf_reports.menu_aged_trial_balance': 'account.account_reports_partners_reports_menu',
    'accounting_pdf_reports.menu_account_report': 'account.account_reports_taxes_and_fiscal_menu',
    'accounting_pdf_reports.menu_account_reports': 'account.account_account_menu',
    'om_account_check_printing.menu_check_format': 'account.account_invoicing_menu',
    'om_account_followup.om_account_followup_menu': 'account.account_invoicing_menu',
    'om_account_asset.menu_action_account_asset_asset_list_normal_purchase':
        'om_account_accountant.menu_account_management_config',
    'om_account_budget.menu_account_budget_position': 'om_account_accountant.menu_account_management_config',
    'om_recurring_payments.menu_recurring_template': 'om_account_accountant.menu_account_management_config',
    'om_fiscal_year.menu_account_period_closing_task': 'om_account_accountant.menu_account_management_config',
}
# the folders replaced by the ones of the account module, or holding a single menu
REMOVED = (
    'accounting_pdf_reports.menu_finance_legal_statement',
    'accounting_pdf_reports.menu_finance_partner_reports',
    'accounting_pdf_reports.menu_finance_reports_settings',
    'om_account_asset.menu_finance_entries_assets',
    'om_account_followup.om_account_followup_main_menu',
    'om_recurring_payments.menu_recurring_payments',
    'om_account_accountant.menu_account_templates',
)


@tagged('post_install', '-at_install')
class TestMenus(TransactionCase):

    def test_menus_are_arranged(self):
        for xmlid, parent in PARENTS.items():
            with self.subTest(menu=xmlid):
                self.assertEqual(self.env.ref(xmlid).parent_id, self.env.ref(parent))
        for xmlid in REMOVED:
            self.assertFalse(self.env.ref(xmlid, raise_if_not_found=False), xmlid)

    def test_no_two_menus_share_a_place(self):
        """ Menus with the same sequence under the same parent come in no given order. """
        roots = self.env.ref('account.menu_finance')
        menus = self.env['ir.ui.menu'].search([('id', 'child_of', roots.ids)])
        ours = self.env['ir.model.data'].search([
            ('model', '=', 'ir.ui.menu'), ('res_id', 'in', menus.ids), ('module', '!=', 'account'),
        ])
        for menu in self.env['ir.ui.menu'].browse(ours.mapped('res_id')):
            clashes = menu.parent_id.child_id.filtered(lambda other: other != menu and other.sequence == menu.sequence)
            self.assertFalse(clashes, '%s shares its place with %s' % (menu.complete_name, clashes.mapped('name')))

    def test_accountant_sees_the_daily_work(self):
        accountant = new_test_user(
            self.env, login='menu_accountant', groups='account.group_account_user',
            company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        visible = self.env['ir.ui.menu'].with_user(accountant)._visible_menu_ids()
        for xmlid in ('om_account_reconcile.menu_bank_reconciliation',
                      'om_account_reconcile.menu_open_items_reconciliation',
                      'om_account_reconcile.menu_move_line_match',
                      'om_account_budget.menu_account_budget',
                      'om_recurring_payments.menu_recurring_payment',
                      'om_account_cash_forecast.menu_cash_forecast_item',
                      'accounting_pdf_reports.menu_action_account_moves_ledger_general',
                      'accounting_pdf_reports.menu_account_report_bs',
                      'accounting_pdf_reports.menu_account_report'):
            self.assertIn(self.env.ref(xmlid).id, visible, xmlid)
