# Preview as a user: the screens of another user, read only, in the
# administrator's own session.
import time

from odoo.exceptions import UserError
from odoo.http import root
from odoo.tests import HttpCase, new_test_user, tagged

from .audit import lines_after_transaction


@tagged('post_install', '-at_install')
class TestPreview(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-preview-pw'
        cls.manager = new_test_user(
            cls.env, 'om_preview_manager', password=cls.password,
            groups='base.group_user,base.group_system,om_access_manager.group_access_manager')
        cls.user = new_test_user(cls.env, 'om_preview_user', groups='base.group_user,base.group_partner_manager',
                                 password=cls.password)
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.discuss = cls.env.ref('mail.menu_root_discuss')
        cls.mine = cls.env['res.partner'].create({'name': 'Previewed Own'})
        cls.other = cls.env['res.partner'].create({'name': 'Previewed Other'})
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Previewed Profile',
            'user_ids': [(6, 0, cls.user.ids)],
            'hidden_menu_ids': [(6, 0, cls.discuss.ids)],
            'model_ids': [(0, 0, {
                'model_id': partner_model.id,
                'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': True,
                'domain': repr([('id', '=', cls.mine.id)]),
            })],
            'button_ids': [(0, 0, {
                'model_id': partner_model.id, 'button_type': 'object',
                'button_name': 'action_archive', 'mode': 'block',
            })],
        })

    def setUp(self):
        super().setUp()
        self.authenticate(self.manager.login, self.password)

    def _call(self, model, method, args, kwargs=None, route='call_kw'):
        return self.make_jsonrpc_request(f'/web/dataset/{route}/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {},
        })

    def _error(self, model, method, args, kwargs=None, route='call_kw'):
        """ The message of the error a call answers with. """
        response = self.url_open(f'/web/dataset/{route}/{model}/{method}', json={
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}},
        })
        return response.json()['error']['data']['message']

    def _start(self, user=None):
        return self._call('res.users', 'action_om_preview', [(user or self.user).ids], route='call_button')

    def _menu_ids(self):
        return {int(key) for key in self.url_open('/web/webclient/load_menus').json() if key.isdigit()}

    def test_who_may_preview(self):
        self.assertTrue(self.user._om_preview_refusal(self.user))
        self.assertFalse(self.user._om_preview_refusal(self.manager))
        self.assertTrue(self.manager._om_preview_refusal(self.manager))
        self.assertTrue(self.env.ref('base.user_admin')._om_preview_refusal(self.manager))
        # an access manager outside Settings never reads more through a preview
        manager = new_test_user(self.env, 'om_preview_small', groups='base.group_user,'
                                'om_access_manager.group_access_manager')
        self.assertTrue(self.user._om_preview_refusal(manager))
        plain = new_test_user(self.env, 'om_preview_plain', groups='base.group_user')
        self.assertFalse(plain._om_preview_refusal(manager))

    def test_the_session_is_seen_as_the_user(self):
        self.assertIn(self.discuss.id, self._menu_ids())
        result = self._start()
        self.assertEqual(result['type'], 'ir.actions.act_url')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info['uid'], self.user.id)
        self.assertEqual(info['om_preview']['name'], self.user.name)
        self.assertEqual(info['om_preview']['profiles'], ['Previewed Profile'])
        self.assertIn('o_om_preview', info['om_access_classes'])
        # the page of the web client too, although /odoo is served without a user
        self.assertIn('"om_preview"', self.url_open('/odoo').text)
        self.assertNotIn(self.discuss.id, self._menu_ids())
        rows = self._call('res.partner', 'search_read', [[('id', 'in', [self.mine.id, self.other.id])], ['name']])
        self.assertEqual([row['id'] for row in rows], [self.mine.id])
        # and back
        result = self.make_jsonrpc_request('/om_access_manager/preview/stop')
        self.assertIn('/odoo', result['url'])
        self.assertEqual(self.make_jsonrpc_request('/web/session/get_session_info')['uid'], self.manager.id)
        self.assertIn(self.discuss.id, self._menu_ids())

    def test_nothing_is_saved(self):
        self._start()
        self.assertIn('preview', self._error('res.partner', 'web_save', [self.mine.ids, {'name': 'Changed'}],
                                             {'specification': {}}))
        self.assertEqual(self.mine.name, 'Previewed Own')
        self.assertIn('preview', self._error('res.partner', 'create', [{'name': 'Created in a preview'}]))
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Created in a preview')]))

    def test_buttons_say_what_the_user_may_do(self):
        self._start()
        # blocked for the user: the profile's refusal
        self.assertIn('not allowed to use this button',
                      self._error('res.partner', 'action_archive', [self.mine.ids], route='call_button'))
        # allowed: said, not run
        self.assertIn('%s may use this' % self.user.name,
                      self._error('res.partner', 'action_unarchive', [self.mine.ids], route='call_button'))
        self.assertTrue(self.mine.active)

    def test_server_actions_run_read_only(self):
        """ Menus open server actions that pick a view: they run in a preview,
        and what one would save is refused. """
        partner_model = self.env['ir.model']._get('res.partner')
        opens = self.env['ir.actions.server'].create({
            'name': 'OM Open Partners', 'model_id': partner_model.id, 'state': 'code',
            'code': "action = {'type': 'ir.actions.act_window', 'res_model': 'res.partner', 'views': [[False, 'list']]}",
        })
        saves = self.env['ir.actions.server'].create({
            'name': 'OM Save a Partner', 'model_id': partner_model.id, 'state': 'code',
            'code': "env['res.partner'].create({'name': 'Saved in a preview'})",
        })
        self._start()
        result = self.make_jsonrpc_request('/web/action/run', {'action_id': opens.id})
        self.assertEqual(result['res_model'], 'res.partner')
        response = self.url_open('/web/action/run', json={
            'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {'action_id': saves.id}})
        self.assertIn('preview', response.json()['error']['data']['message'])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Saved in a preview')]))

    def test_reads_are_logged_as_the_administrator(self):
        self.env['om.user.audit.rule'].create({'name': 'Partners', 'model_ids': [
            (6, 0, self.env['ir.model']._get('res.partner').ids)], 'log_read': True})
        self._start()
        with lines_after_transaction(self.env) as lines:
            self._call('res.partner', 'web_read', [self.mine.ids], {'specification': {'name': {}}})
        reads = [line for line in lines if line['event'] == 'read']
        self.assertTrue(reads)
        self.assertEqual({line['user_id'] for line in reads}, {self.manager.id})
        self.assertIn(self.user.name, reads[0]['detail'])

    def test_an_expired_preview_ends(self):
        self._start()
        session = self.opener.cookies.get('session_id')
        self.assertTrue(session)
        self.assertEqual(self.make_jsonrpc_request('/web/session/get_session_info')['uid'], self.user.id)
        store = root.session_store
        stored = store.get(session)
        stored['om_access_preview'] = dict(stored['om_access_preview'], until=time.time() - 1)
        store.save(stored)
        self.assertEqual(self.make_jsonrpc_request('/web/session/get_session_info')['uid'], self.manager.id)

    def test_a_profile_previews_its_users_only(self):
        Profile = self.env['om.access.profile'].with_user(self.manager)
        empty = Profile.create({'name': 'Nobody yet'})
        with self.assertRaisesRegex(UserError, 'No user has this profile yet'):
            empty.action_test_user()
        action = Profile.browse(self.profile.id).action_test_user()
        wizard = self.env['om.access.test.user'].with_user(self.manager).with_context(
            action['context']).create({})
        self.assertEqual(wizard.user_id, self.user)
        self.assertEqual(wizard.preview_user_ids, self.user)
        outsider = new_test_user(self.env, 'om_preview_outsider', groups='base.group_user')
        wizard.user_id = outsider
        with self.assertRaisesRegex(UserError, 'does not have the profile'):
            wizard.action_open_preview()

    def test_web_client_in_a_preview(self):
        self.manager.password = self.manager.login
        self.start_tour(f'/odoo/action-base.action_res_users/{self.user.id}', 'om_access_manager_preview',
                        login=self.manager.login, timeout=120)

    def test_add_existing_users_from_the_profile(self):
        target = new_test_user(self.env, 'om_add_users_target', groups='base.group_user')
        profile = self.env['om.access.profile'].create({'name': 'Add Users Profile'})
        self.manager.password = self.manager.login
        self.start_tour(f'/odoo/action-om_access_manager.om_access_profile_action/{profile.id}',
                        'om_access_manager_add_users', login=self.manager.login, timeout=120)
        self.assertEqual(profile.user_ids, target)


@tagged('post_install', '-at_install')
class TestTickToGrant(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, 'om_tick_manager',
            groups='base.group_user,base.group_system,om_access_manager.group_access_manager')
        privilege = cls.env['res.groups.privilege'].create({'name': 'OM Tick App'})
        cls.app_user = cls.env['res.groups'].create({'name': 'User', 'privilege_id': privilege.id})
        cls.app_manager = cls.env['res.groups'].create({
            'name': 'Manager', 'privilege_id': privilege.id, 'implied_ids': [(4, cls.app_user.id)]})
        cls.root = cls.env['ir.ui.menu'].create({
            'name': 'OM Tick App', 'group_ids': [(6, 0, (cls.app_user | cls.app_manager).ids)]})
        cls.env['ir.ui.menu'].create({
            'name': 'OM Tick Records', 'parent_id': cls.root.id,
            'action': f'ir.actions.act_window,{cls.env.ref("base.action_partner_form").id}'})
        cls.user = new_test_user(cls.env, 'om_tick_user', groups='base.group_user')
        cls.profile = cls.env['om.access.profile'].create({'name': 'Tick', 'user_ids': [(6, 0, cls.user.ids)]})

    def test_app_access(self):
        Profile = self.env['om.access.profile'].with_user(self.manager)
        access = Profile.browse(self.profile.id).om_app_access(self.user.ids)[self.root.id]
        self.assertFalse(access['open'])
        self.assertEqual(access['grant']['id'], self.app_user.id)
        self.assertEqual(access['grant']['name'], 'OM Tick App / User')
        self.assertEqual(set(access['group_ids']), {self.app_user.id, self.app_manager.id})
        # a user who already has the app
        holder = new_test_user(self.env, 'om_tick_holder', groups='base.group_user')
        holder.group_ids |= self.app_user
        self.assertTrue(Profile.browse(self.profile.id).om_app_access(holder.ids)[self.root.id]['open'])
        # nobody yet: nothing to tell
        self.assertTrue(Profile.om_app_access([])[self.root.id]['open'])

    def test_ticking_an_app_gives_it(self):
        self.start_tour(f'/odoo/action-om_access_manager.om_access_profile_action/{self.profile.id}',
                        'om_access_manager_tick_grant', login=self.manager.login, timeout=120)
        self.assertEqual(self.profile.granted_group_ids, self.app_user)
        self.assertIn(self.app_user, self.user.all_group_ids)

    def test_unticking_an_app_takes_it_back(self):
        self.profile.granted_group_ids = self.app_user
        self.start_tour(f'/odoo/action-om_access_manager.om_access_profile_action/{self.profile.id}',
                        'om_access_manager_untick_grant', login=self.manager.login, timeout=120)
        self.assertFalse(self.profile.granted_group_ids)
        self.assertIn(self.root, self.profile.hidden_menu_ids)
        self.assertNotIn(self.app_user, self.user.all_group_ids)
