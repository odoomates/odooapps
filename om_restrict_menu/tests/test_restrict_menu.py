<<<<<<< HEAD
import json
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
=======
# -*- coding: utf-8 -*-
try:
    from unittest.mock import patch
except ImportError:  # Python 2: Odoo 10
    from mock import patch

from odoo.tests import common

from odoo.addons.om_restrict_menu.models import compat
from odoo.addons.web.controllers.main import Home

COMPAT_MODULE = 'odoo.addons.om_restrict_menu.models.compat'


def post_install(cls):
    """ Run after every module is installed: tagged() from Odoo 12, the decorators before """
    if hasattr(common, 'tagged'):
        return common.tagged('post_install', '-at_install')(cls)
    return common.post_install(True)(common.at_install(False)(cls))


class FakeRequest(object):
    """ The request of the menus, with only its cookies """

    def __init__(self, cids):
        self.httprequest = type('HttpRequest', (object,), {'cookies': {'cids': cids}})()


class HideMenuCase(object):
    """ The users, companies and menus of the tests; mixed in a TransactionCase or an HttpCase. """

    def setUp(self):
        super(HideMenuCase, self).setUp()
        self.company = self.env.user.company_id
        self.branch = self.env['res.company'].create({'name': 'Hide Menu Branch'})
        self.user = self._new_user('hide_menu_user', ['base.group_user'])
        self.other = self._new_user('hide_menu_other', ['base.group_user'])
        self.admin = self._new_user('hide_menu_admin', ['base.group_user', 'base.group_system'])
        Menu = self.env['ir.ui.menu']
        self.app = Menu.create({'name': 'Hide Menu App'})
        self.first = Menu.create({'name': 'First', 'parent_id': self.app.id, 'sequence': 1,
                                  'action': self._partner_action('First')})
        self.folder = Menu.create({'name': 'Folder', 'parent_id': self.app.id, 'sequence': 2})
        self.leaf = Menu.create({'name': 'Leaf', 'parent_id': self.folder.id,
                                 'action': self._partner_action('Leaf')})

    def _new_user(self, login, groups):
        """ A user of both companies, whose password is the login """
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'password': login,
            'company_id': self.company.id, 'company_ids': [(6, 0, (self.company + self.branch).ids)],
            'groups_id': [(6, 0, [self.env.ref(group).id for group in groups])]})

    def _partner_action(self, name):
        action = self.env['ir.actions.act_window'].create({'name': name, 'res_model': 'res.partner'})
        return 'ir.actions.act_window,%s' % action.id

    def _as_current(self, user, company):
        """ The menus of ``user`` while ``company`` is the current company """
        Menu = compat.as_user(self.env['ir.ui.menu'], user)
        if hasattr(self.env, 'company'):
            return Menu.with_context(allowed_company_ids=[company.id])
        user.company_id = company
        return Menu

    def _menus(self, user, company=None):
        """ The menu tree of the web client, as a dict {id: menu}, with the root under 'root' """
        root = self._as_current(user, company or self.company).load_menus(False)
        menus = {'root': root}

        def add(menu):
            for child in menu.get('children') or []:
                menus[child['id']] = child
                add(child)

        add(root)
        return menus

    @staticmethod
    def _children(menu):
        return [child['id'] for child in menu.get('children') or []]

    def _app2(self):
        app2 = self.env['ir.ui.menu'].create({'name': 'Hide Menu Other App'})
        self.env['ir.ui.menu'].create({'name': 'Other', 'parent_id': app2.id,
                                       'action': self._partner_action('Other')})
        return app2


@post_install
class TestHideMenu(HideMenuCase, common.TransactionCase):
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

    def test_hidden_for_the_user_only(self):
        self.user.om_hidden_menu_ids = self.first
        self.assertNotIn(self.first.id, self._menus(self.user))
<<<<<<< HEAD
        self.assertNotIn(self.first.id, self._menus(self.user)[self.app.id]['children'])
=======
        self.assertNotIn(self.first.id, self._children(self._menus(self.user)[self.app.id]))
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
        self.assertIn(self.first.id, self._menus(self.other))

    def test_both_sides_are_the_same_rule(self):
        self.user.om_hidden_menu_ids = self.first
        self.assertEqual(self.first.om_hidden_user_ids, self.user)
        self.leaf.om_hidden_company_ids = self.branch
        self.assertEqual(self.branch.om_hidden_menu_ids, self.leaf)

    def test_hidden_in_the_current_company_only(self):
        self.branch.om_hidden_menu_ids = self.first
<<<<<<< HEAD
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
=======
        self.assertNotIn(self.first.id, self._menus(self.user, self.branch))
        self.assertNotIn(self.first.id, self._menus(self.other, self.branch))
        self.assertIn(self.first.id, self._menus(self.user, self.company))

    def test_current_company_from_the_cookie(self):
        """ From Odoo 13 the menus are fetched without a context: the cids cookie tells the current company. """
        if not hasattr(self.env, 'company'):
            self.skipTest('the current company is the company of the user before Odoo 13')
        env = compat.as_user(self.env['ir.ui.menu'], self.user).env
        for cids, company in [('%s,%s' % (self.branch.id, self.company.id), self.branch),
                              ('%s-%s' % (self.company.id, self.branch.id), self.company),
                              ('999999', self.company), ('', self.company)]:
            with patch(COMPAT_MODULE + '.request', FakeRequest(cids)):
                self.assertEqual(compat.current_company(env), company, cids)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

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
<<<<<<< HEAD
        self.assertNotIn(self.app.id, menus['root']['children'])

    def test_the_app_opens_a_visible_menu(self):
        self.assertEqual(self._menus(self.user)[self.app.id]['actionID'], self.first.action.id)
        self.user.om_hidden_menu_ids = self.first
        self.assertEqual(self._menus(self.user)[self.app.id]['actionID'], self.leaf.action.id)
=======
        self.assertNotIn(self.app.id, self._children(menus['root']))
        self.assertNotIn(self.app.id, menus['root']['all_menu_ids'])

    def test_the_app_opens_a_visible_menu(self):
        """ The web client opens the first menu of an app with an action """
        def first_action(menu):
            for child in menu.get('children') or []:
                found = child['action'] and child['id'] or first_action(child)
                if found:
                    return found
            return False

        self.assertEqual(first_action(self._menus(self.user)[self.app.id]), self.first.id)
        self.user.om_hidden_menu_ids = self.first
        self.assertEqual(first_action(self._menus(self.user)[self.app.id]), self.leaf.id)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

    def test_the_cached_menus_are_not_changed(self):
        self.user.om_hidden_menu_ids = self.first
        self.assertNotIn(self.first.id, self._menus(self.user))
        self.user.om_hidden_menu_ids = False
        self.assertIn(self.first.id, self._menus(self.user))
<<<<<<< HEAD
        self.assertIn(self.first.id, self._menus(self.user)[self.app.id]['children'])
=======
        self.assertIn(self.first.id, self._children(self._menus(self.user)[self.app.id]))
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

    def test_the_administrators_keep_the_settings(self):
        settings = self.env.ref('base.menu_administration')
        users = self.env.ref('base.menu_users')
        self.company.om_hidden_menu_ids = settings + users + self.first
        menus = self._menus(self.admin)
        self.assertIn(settings.id, menus)
        self.assertIn(users.id, menus)
        self.assertNotIn(self.first.id, menus)

<<<<<<< HEAD
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
=======
    def test_the_menus_follow_the_company(self):
        """ load_menus() and load_menus_root() are cached per user: the menus hidden in a company must not stay
        hidden in the others. """
        self.branch.om_hidden_menu_ids = self.app
        for company, visible in [(self.branch, False), (self.company, True), (self.branch, False)]:
            root = self._as_current(self.user, company).load_menus_root()
            self.assertEqual(self.app.id in self._children(root), visible, company.name)
            self.assertEqual(self.app.id in root['all_menu_ids'], visible, company.name)
            self.assertEqual(self.app.id in self._menus(self.user, company), visible, company.name)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

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
<<<<<<< HEAD
        self.assertEqual(menus['root']['children'], [self.app.id])
        root = self.env['ir.ui.menu'].with_user(self.user).load_menus_root()
        self.assertEqual([menu['id'] for menu in root['children']], [self.app.id])
=======
        self.assertEqual(self._children(menus['root']), [self.app.id])
        root = compat.as_user(self.env['ir.ui.menu'], self.user).load_menus_root()
        self.assertEqual(self._children(root), [self.app.id])
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
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
<<<<<<< HEAD
        self.user.write({'om_hidden_menu_ids': [Command.set(self.first.ids)],
                         'om_visible_menu_ids': [Command.set(self.app.ids)]})
=======
        self.user.write({'om_hidden_menu_ids': [(6, 0, self.first.ids)],
                         'om_visible_menu_ids': [(6, 0, self.app.ids)]})
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
        self.other.om_hidden_menu_ids = self.leaf
        Wizard = self.env['om.restrict.menu.set'].with_context(active_model='res.users', active_ids=self.other.ids)
        wizard = Wizard.create({'source_user_id': self.user.id})
        self.assertEqual(wizard.user_ids, self.other)
        self.assertEqual(wizard.hidden_menu_ids, self.first)
        self.assertEqual(wizard.visible_menu_ids, self.app)
        wizard.action_apply()
        self.assertEqual(self.other.om_hidden_menu_ids, self.first)
        self.assertEqual(self.other.om_visible_menu_ids, self.app)

<<<<<<< HEAD
        Wizard.create({'user_ids': [Command.set((self.other + self.admin).ids)], 'mode': 'add',
                       'hidden_menu_ids': [Command.set(self.leaf.ids)],
                       'visible_menu_ids': [Command.set(app2.ids)]}).action_apply()
=======
        Wizard.create({'user_ids': [(6, 0, (self.other + self.admin).ids)], 'mode': 'add',
                       'hidden_menu_ids': [(6, 0, self.leaf.ids)],
                       'visible_menu_ids': [(6, 0, app2.ids)]}).action_apply()
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
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
<<<<<<< HEAD
                                       'action': f'{action._name},{action.id}'})
        self.assertFalse(self.user.om_home_action_hidden)

=======
                                       'action': '%s,%s' % (action._name, action.id)})
        self.assertFalse(self.user.om_home_action_hidden)

    def test_the_home_action_of_the_web_client(self):
        """ The web client reads the Home Action of the user to open it: not one in hidden menus. """
        action = self.first.action
        self.user.action_id = action.id
        Users = compat.as_user(self.env['res.users'], self.user)

        def home_action():
            values = Users.browse(self.user.id).read(['action_id'])[0]['action_id']
            return values and values[0]

        self.assertEqual(home_action(), action.id)
        self.user.om_hidden_menu_ids = self.first
        self.assertFalse(home_action())
        # any other read keeps the action
        self.assertEqual(Users.browse(self.user.id).read(['action_id', 'name'])[0]['action_id'][0], action.id)

>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
    def test_everything_hidden_for_the_user(self):
        """ The user form lists every menu hidden for the user, and why. """
        self.assertIn('Nothing is hidden', self.user.om_hidden_menus_summary)
        self.user.om_hidden_menu_ids = self.first
        self.branch.om_hidden_menu_ids = self.leaf
        app2 = self._app2()
        self.user.om_visible_menu_ids = self.app
<<<<<<< HEAD
=======
        self.user.invalidate_cache()
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
        summary = self.user.om_hidden_menus_summary
        self.assertIn(self.first.complete_name, summary)
        self.assertIn('Hidden for the user, in every company', summary)
        self.assertIn(self.leaf.complete_name, summary)
        self.assertIn('Hidden in Hide Menu Branch, while it is the current company', summary)
        self.assertIn('Not in the Visible Apps', summary)
<<<<<<< HEAD
        self.assertNotIn(f'<td>{self.app.complete_name}</td>', summary)
        self.assertIn(f'<td>{app2.complete_name}</td>', summary)
        # the apps the user could not open anyway are not listed
        self.assertNotIn(f'<td>{self.env.ref("base.menu_administration").complete_name}</td>', summary)
=======
        self.assertNotIn('<td>%s</td>' % self.app.complete_name, summary)
        self.assertIn('<td>%s</td>' % app2.complete_name, summary)
        # the apps the user could not open anyway are not listed
        self.assertNotIn('<td>%s</td>' % self.env.ref('base.menu_administration').complete_name, summary)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

        self.admin.om_hidden_menu_ids = self.env.ref('base.menu_users')
        self.assertIn('administrators always keep the Settings app', self.admin.om_hidden_menus_summary)

    def test_the_search_in_an_app(self):
        found = self.env['ir.ui.menu'].search([('parent_id', 'child_of', self.app.id)])
        self.assertEqual(found, self.app + self.first + self.folder + self.leaf)


<<<<<<< HEAD
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

    def _session_info(self):
        response = self.url_open('/web/session/get_session_info', data=json.dumps({'params': {}}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()['result']

    def test_the_home_action_of_the_session(self):
        """ The web client opens the first visible app instead of a Home Action in hidden menus. """
        self.user.action_id = self.first.action.id
        self.authenticate(self.user.login, self.user.login)
        self.assertEqual(self._session_info()['home_action_id'], self.first.action.id)
        self.user.om_hidden_menu_ids = self.first
        self.assertFalse(self._session_info()['home_action_id'])
=======
@post_install
class TestHideMenuRequest(HideMenuCase, common.HttpCase):

    def test_the_menus_request_follows_the_company_switcher(self):
        if not hasattr(Home, 'web_load_menus'):
            self.skipTest('the menus come with the page before Odoo 13')
        self.branch.om_hidden_menu_ids = self.first
        self.authenticate(self.user.login, self.user.login)
        for current, visible in [(self.branch, False), (self.company, True)]:
            self.opener.cookies.set('cids', '%s,%s' % (current.id, (self.company + self.branch - current).id))
            response = self.url_open('/web/webclient/load_menus/1')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(('"id": %s,' % self.first.id) in response.text, visible, current.name)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
