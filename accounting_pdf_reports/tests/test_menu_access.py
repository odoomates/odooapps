from odoo import Command
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

FINANCIAL_MENUS = (
    'accounting_pdf_reports.menu_account_report_bs',
    'accounting_pdf_reports.menu_account_report_pl',
    'accounting_pdf_reports.menu_general_ledger',
    'accounting_pdf_reports.menu_general_balance_report',
    'accounting_pdf_reports.menu_account_report',
    'accounting_pdf_reports.menu_print_journal',
)
PARTNER_MENUS = (
    'accounting_pdf_reports.menu_partner_ledger',
    'accounting_pdf_reports.menu_aged_trial_balance',
    'accounting_pdf_reports.menu_aged_receivable',
    'accounting_pdf_reports.menu_aged_payable',
)


@tagged('post_install', '-at_install')
class TestMenuAccess(AccountTestInvoicingCommon):
    """ The report menus show to the users who can run the reports, and only to them. """

    def _user(self, login, group):
        return new_test_user(self.env, login=login, groups=group, company_id=self.env.company.id,
                             company_ids=[Command.set(self.env.company.ids)])

    def _visible(self, user, xmlids):
        visible = self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()
        return {xmlid for xmlid in xmlids if self.env.ref(xmlid).id in visible}

    def _run(self, user, xmlid):
        """ Open the wizard of the menu as `user` and compute the report. """
        action = self.env.ref(xmlid).action
        wizard = self.env[action.res_model].with_user(user).with_context(active_model=action.res_model).create({})
        return wizard.check_report()

    def test_auditor_and_administrator_run_the_reports(self):
        self.init_invoice('out_invoice', amounts=[100.0], invoice_date='2025-06-01', post=True)
        for login, group in (('report_auditor', 'account.group_account_readonly'),
                             ('report_admin', 'account.group_account_manager')):
            user = self._user(login, group)
            with self.subTest(group=group):
                self.assertEqual(self._visible(user, FINANCIAL_MENUS + PARTNER_MENUS),
                                 set(FINANCIAL_MENUS + PARTNER_MENUS))
                for xmlid in ('accounting_pdf_reports.menu_general_balance_report',
                              'accounting_pdf_reports.menu_aged_trial_balance',
                              'accounting_pdf_reports.menu_partner_ledger'):
                    self.assertEqual(self._run(user, xmlid)['type'], 'ir.actions.report', xmlid)

    def test_invoicing_user_sees_the_partner_reports(self):
        user = self._user('report_billing', 'account.group_account_invoice')
        self.assertEqual(self._visible(user, FINANCIAL_MENUS + PARTNER_MENUS), set(PARTNER_MENUS))
        self.assertEqual(self._run(user, 'accounting_pdf_reports.menu_aged_trial_balance')['type'], 'ir.actions.report')
