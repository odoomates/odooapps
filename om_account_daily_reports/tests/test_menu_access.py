from odoo import Command
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

BOOK_MENUS = (
    'om_account_daily_reports.menu_cashbook',
    'om_account_daily_reports.menu_bankbook',
    'om_account_daily_reports.menu_daybook',
)


@tagged('post_install', '-at_install')
class TestMenuAccess(AccountTestInvoicingCommon):

    def test_books_show_to_the_users_who_can_open_them(self):
        Menu = self.env['ir.ui.menu']
        for login, group, expected in (('book_auditor', 'account.group_account_readonly', set(BOOK_MENUS)),
                                       ('book_admin', 'account.group_account_manager', set(BOOK_MENUS)),
                                       ('book_billing', 'account.group_account_invoice', set())):
            user = new_test_user(self.env, login=login, groups=group, company_id=self.env.company.id,
                                 company_ids=[Command.set(self.env.company.ids)])
            with self.subTest(group=group):
                visible = Menu.with_user(user)._visible_menu_ids()
                self.assertEqual({xmlid for xmlid in BOOK_MENUS if self.env.ref(xmlid).id in visible}, expected)
                for xmlid in expected:
                    action = self.env.ref(xmlid).action
                    self.env[action.res_model].with_user(user).create({})
