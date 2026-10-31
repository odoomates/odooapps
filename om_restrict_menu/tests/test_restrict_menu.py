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

    def test_the_app_switcher_of_the_website(self):
        """ website caches load_menus_root() again, above this module, for its app switcher: the roots still
        follow the company, whichever asks first. """
        if 'website' not in self.env.registry._init_modules:
            self.skipTest('website is not installed')
        self.branch.om_hidden_menu_ids = self.app
        Menu = self.env['ir.ui.menu'].with_user(self.user).with_context(force_action=True)
        for company, visible in [(self.company, True), (self.branch, False), (self.company, True)]:
            root = Menu.with_context(allowed_company_ids=company.ids).load_menus_root()
            self.assertEqual(self.app.id in [menu['id'] for menu in root['children']], visible, company.name)


    def _app2(self):
        app2 = self.env['ir.ui.menu'].create({'name': 'Hide Menu Other App'})
        self.env['ir.ui.menu'].create({'name': 'Other', 'parent_id': app2.id, 'action': self._partner_action('Other')})
        return app2

    def test_visible_apps_only(self):
        """ With Visible Apps, every other app is hidden, also one created later; the hidden menus still hide
        menus inside the visible apps. """
        self.user.om_visible_menu_ids = self.app
        self.user.om_hidden_menu_ids = self.folder
        app2 = self._app2()
        menus = self._menus(self.user)
        self.assertIn(self.app.id, menus)
        self.assertIn(self.first.id, menus)
        self.assertNotIn(self.folder.id, menus)
        self.assertNotIn(app2.id, menus)
        self.assertEqual(menus['root']['children'], [self.app.id])
        root = self.env['ir.ui.menu'].with_user(self.user).load_menus_root()
        self.assertEqual([menu['id'] for menu in root['children']], [self.app.id])
        self.assertIn(app2.id, self._menus(self.other))
        self.assertEqual(self.app.om_visible_user_ids, self.user)

    def test_visible_apps_and_the_company(self):
        """ The menus hidden in the current company are hidden in the visible apps too. """
        self.user.om_visible_menu_ids = self.app
        self.branch.om_hidden_menu_ids = self.first
        self.assertNotIn(self.first.id, self._menus(self.user, self.branch))
        self.assertIn(self.first.id, self._menus(self.user, self.company))

    def test_visible_apps_keep_the_settings_of_the_administrators(self):
        settings = self.env.ref('base.menu_administration')
        self.admin.om_visible_menu_ids = self.app
        menus = self._menus(self.admin)
        self.assertIn(settings.id, menus)
        self.assertIn(self.app.id, menus)
        self.assertNotIn(self._app2().id, self._menus(self.admin))

    def test_the_menus_of_several_users(self):
        """ Copy the menus of a user to others, replacing theirs or adding to them. """
        app2 = self._app2()
        self.user.write({'om_hidden_menu_ids': [Command.set(self.first.ids)],
                         'om_visible_menu_ids': [Command.set(self.app.ids)]})
        self.other.om_hidden_menu_ids = self.leaf
        Wizard = self.env['om.restrict.menu.set'].with_context(active_model='res.users', active_ids=self.other.ids)
        wizard = Wizard.create({'source_user_id': self.user.id})
        self.assertEqual(wizard.user_ids, self.other)
        self.assertEqual(wizard.hidden_menu_ids, self.first)
        self.assertEqual(wizard.visible_menu_ids, self.app)
        wizard.action_apply()
        self.assertEqual(self.other.om_hidden_menu_ids, self.first)
        self.assertEqual(self.other.om_visible_menu_ids, self.app)

        Wizard.create({'user_ids': [Command.set((self.other + self.admin).ids)], 'mode': 'add',
                       'hidden_menu_ids': [Command.set(self.leaf.ids)],
                       'visible_menu_ids': [Command.set(app2.ids)]}).action_apply()
        self.assertEqual(self.other.om_hidden_menu_ids, self.first + self.leaf)
        self.assertEqual(self.other.om_visible_menu_ids, self.app + app2)
        self.assertEqual(self.admin.om_hidden_menu_ids, self.leaf)

    def test_a_home_action_in_hidden_menus(self):
        """ The user form warns when the Home Action opens only from hidden menus. """
        action = self.first.action
        self.user.action_id = action.id
        self.assertFalse(self.user.om_home_action_hidden)
        self.user.om_hidden_menu_ids = self.first
        self.assertTrue(self.user.om_home_action_hidden)
        self.user.om_hidden_menu_ids = False
        self.user.om_visible_menu_ids = self._app2()
        self.assertTrue(self.user.om_home_action_hidden, 'the app of the action is out of the visible apps')
        self.user.om_visible_menu_ids = self.app
        self.assertFalse(self.user.om_home_action_hidden)
        # an action opened from a visible menu too is not hidden
        self.user.om_hidden_menu_ids = self.first
        self.env['ir.ui.menu'].create({'name': 'First Again', 'parent_id': self.folder.id,
                                       'action': f'{action._name},{action.id}'})
        self.assertFalse(self.user.om_home_action_hidden)

    def test_everything_hidden_for_the_user(self):
        """ The user form lists every menu hidden for the user, and why. """
        self.assertIn('Nothing is hidden', self.user.om_hidden_menus_summary)
        self.user.om_hidden_menu_ids = self.first
        self.branch.om_hidden_menu_ids = self.leaf
        app2 = self._app2()
        self.user.om_visible_menu_ids = self.app
        summary = self.user.om_hidden_menus_summary
        self.assertIn(self.first.complete_name, summary)
        self.assertIn('Hidden for the user, in every company', summary)
        self.assertIn(self.leaf.complete_name, summary)
        self.assertIn('Hidden in Hide Menu Branch, while it is the current company', summary)
        self.assertIn('Not in the Visible Apps', summary)
        self.assertNotIn(f'<td>{self.app.complete_name}</td>', summary)
        self.assertIn(f'<td>{app2.complete_name}</td>', summary)
        # the apps the user could not open anyway are not listed
        self.assertNotIn(f'<td>{self.env.ref("base.menu_administration").complete_name}</td>', summary)

        self.admin.om_hidden_menu_ids = self.env.ref('base.menu_users')
        self.assertIn('administrators always keep the Settings app', self.admin.om_hidden_menus_summary)

    def test_the_search_in_an_app(self):
        found = self.env['ir.ui.menu'].search([('parent_id', 'child_of', self.app.id)])
        self.assertEqual(found, self.app + self.first + self.folder + self.leaf)


@tagged('post_install', '-at_install')
class TestHideMenuRequest(HttpCase, HideMenuCase):

    def test_the_menus_request_follows_the_company_switcher(self):
        self.branch.om_hidden_menu_ids = self.first
        self.authenticate(self.user.login, self.user.login)
        for current, visible in [(self.branch, False), (self.company, True)]:
            self.opener.cookies.set('cids', f'{current.id}-{(self.company + self.branch - current).id}')
            response = self.url_open('/web/webclient/load_menus/1')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            menus = response.json()
            self.assertEqual(str(self.first.id) in menus, visible, current.name)

    def test_the_home_action_of_the_session(self):
        """ The web client opens the first visible app instead of a Home Action in hidden menus. """
        self.user.action_id = self.first.action.id
        self.authenticate(self.user.login, self.user.login)
        self.assertEqual(self.make_jsonrpc_request('/web/session/get_session_info')['home_action_id'],
                         self.first.action.id)
        self.user.om_hidden_menu_ids = self.first
        self.assertFalse(self.make_jsonrpc_request('/web/session/get_session_info')['home_action_id'])
