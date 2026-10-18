from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

MENU_MODULE = 'odoo.addons.om_restrict_menu.models.ir_ui_menu'


class HideMenuCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.branch = cls.env['res.company'].create({'name': 'Hide Menu Branch'})
        companies = [Command.set([cls.company.id, cls.branch.id])]
        cls.user = new_test_user(cls.env, 'hide_menu_user', groups='base.group_user',
                                 company_id=cls.company.id, company_ids=companies)
        cls.other = new_test_user(cls.env, 'hide_menu_other', groups='base.group_user',
                                  company_id=cls.company.id, company_ids=companies)
        cls.admin = new_test_user(cls.env, 'hide_menu_admin', groups='base.group_user,base.group_system',
                                  company_id=cls.company.id, company_ids=companies)
        Menu = cls.env['ir.ui.menu']
        cls.app = Menu.create({'name': 'Hide Menu App'})
        cls.first = Menu.create({'name': 'First', 'parent_id': cls.app.id, 'sequence': 1,
                                 'action': cls._partner_action('First')})
        cls.folder = Menu.create({'name': 'Folder', 'parent_id': cls.app.id, 'sequence': 2})
        cls.leaf = Menu.create({'name': 'Leaf', 'parent_id': cls.folder.id,
                                'action': cls._partner_action('Leaf')})

    @classmethod
    def _partner_action(cls, name):
        action = cls.env['ir.actions.act_window'].create({'name': name, 'res_model': 'res.partner'})
        return f'ir.actions.act_window,{action.id}'

    def _menus(self, user, companies=None):
        Menu = self.env['ir.ui.menu'].with_user(user)
        if companies:
            Menu = Menu.with_context(allowed_company_ids=companies.ids)
        return Menu.load_web_menus(False)



@tagged('post_install', '-at_install')
class TestHideMenu(HideMenuCase):

    def test_hidden_for_the_user_only(self):
        self.user.om_hidden_menu_ids = self.first
        self.assertNotIn(self.first.id, self._menus(self.user))
        self.assertNotIn(self.first.id, self._menus(self.user)[self.app.id]['children'])
        self.assertIn(self.first.id, self._menus(self.other))

    def test_both_sides_are_the_same_rule(self):
        self.user.om_hidden_menu_ids = self.first
        self.assertEqual(self.first.om_hidden_user_ids, self.user)
        self.leaf.om_hidden_company_ids = self.branch
        self.assertEqual(self.branch.om_hidden_menu_ids, self.leaf)

    def test_hidden_in_the_current_company_only(self):
        self.branch.om_hidden_menu_ids = self.first
        self.assertNotIn(self.first.id, self._menus(self.user, self.branch + self.company))
        self.assertNotIn(self.first.id, self._menus(self.other, self.branch))
        self.assertIn(self.first.id, self._menus(self.user, self.company + self.branch))

    def test_current_company_from_the_cookie(self):
        """ The menus are fetched without a context: the cids cookie tells the current company. """
        Menu = self.env['ir.ui.menu'].with_user(self.user)
        for cids, company in [(f'{self.branch.id}-{self.company.id}', self.branch),
                              (f'{self.company.id}-{self.branch.id}', self.company),
                              ('999999', self.company), ('', self.company)]:
            fake = SimpleNamespace(httprequest=SimpleNamespace(cookies={'cids': cids}))
            with patch(f'{MENU_MODULE}.request', fake):
                self.assertEqual(Menu._om_current_company(), company, cids)

    def test_sub_menus_and_empty_folders(self):
        self.user.om_hidden_menu_ids = self.folder
        menus = self._menus(self.user)
        self.assertNotIn(self.folder.id, menus)
        self.assertNotIn(self.leaf.id, menus)
        # a folder left with nothing to open goes too
        self.user.om_hidden_menu_ids = self.first + self.leaf
        menus = self._menus(self.user)
        self.assertNotIn(self.folder.id, menus)
        self.assertNotIn(self.app.id, menus)
        self.assertNotIn(self.app.id, menus['root']['children'])

    def test_the_app_opens_a_visible_menu(self):
        self.assertEqual(self._menus(self.user)[self.app.id]['actionID'], self.first.action.id)
        self.user.om_hidden_menu_ids = self.first
        self.assertEqual(self._menus(self.user)[self.app.id]['actionID'], self.leaf.action.id)

    def test_the_cached_menus_are_not_changed(self):
        self.user.om_hidden_menu_ids = self.first
        self.assertNotIn(self.first.id, self._menus(self.user))
        self.user.om_hidden_menu_ids = False
        self.assertIn(self.first.id, self._menus(self.user))
        self.assertIn(self.first.id, self._menus(self.user)[self.app.id]['children'])

    def test_the_administrators_keep_the_settings(self):
        settings = self.env.ref('base.menu_administration')
        users = self.env.ref('base.menu_users')
        self.company.om_hidden_menu_ids = settings + users + self.first
        menus = self._menus(self.admin)
        self.assertIn(settings.id, menus)
        self.assertIn(users.id, menus)
        self.assertNotIn(self.first.id, menus)

    def test_the_roots_follow_the_company(self):
        """ load_menus_root() is cached per user: the roots hidden in a company must not stay hidden in the
        others. """
        self.branch.om_hidden_menu_ids = self.app
        Menu = self.env['ir.ui.menu'].with_user(self.user)

        def roots(company):
            root = Menu.with_context(allowed_company_ids=company.ids).load_menus_root()
            return [menu['id'] for menu in root['children']], root['all_menu_ids']

        for company, visible in [(self.branch, False), (self.company, True), (self.branch, False)]:
            children, all_ids = roots(company)
            self.assertEqual(self.app.id in children, visible, company.name)
            self.assertEqual(self.app.id in all_ids, visible, company.name)


@tagged('post_install', '-at_install')
class TestHideMenuRequest(HttpCase, HideMenuCase):

    def test_the_menus_request_follows_the_company_switcher(self):
        self.branch.om_hidden_menu_ids = self.first
        self.authenticate(self.user.login, self.user.login)
        for current, visible in [(self.branch, False), (self.company, True)]:
            self.opener.cookies.set('cids', f'{current.id}-{(self.company + self.branch - current).id}')
            menus = self.url_open('/web/webclient/load_menus').json()
            self.assertEqual(str(self.first.id) in menus, visible, current.name)
