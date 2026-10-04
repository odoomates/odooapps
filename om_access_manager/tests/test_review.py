# Security regression tests, each through the entry point concerned.
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException


@tagged('post_install', '-at_install')
class TestReview(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-review-pw'
        cls.user = new_test_user(cls.env, 'om_access_review_user',
                                 groups='base.group_user,base.group_partner_manager,base.group_allow_export',
                                 password=cls.password)
        Fields = cls.env['ir.model.fields']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partner = cls.env['res.partner'].create({'name': 'Reviewed', 'email': 'secret@example.com',
                                                     'phone': '111'})
        cls.child = cls.env['res.partner'].create({'name': 'Child', 'parent_id': cls.partner.id, 'phone': '222'})
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Review',
            'user_ids': [(6, 0, cls.user.ids)],
            'field_ids': [
                (0, 0, {'model_id': cls.partner_model.id, 'mode': 'hide',
                        'field_id': Fields._get('res.partner', 'email').id}),
                (0, 0, {'model_id': cls.partner_model.id, 'mode': 'readonly',
                        'field_id': Fields._get('res.partner', 'phone').id}),
            ],
        })

    def setUp(self):
        super().setUp()
        self.authenticate(self.user.login, self.password)

    def _rpc(self, route, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(route, {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}})

    def test_call_button_carries_the_field_guard(self):
        result = self._rpc('/web/dataset/call_button', 'res.partner', 'web_search_read',
                           [[('id', '=', self.partner.id)], {'email': {}}])
        self.assertIs(result['records'][0]['email'], False)

    def test_the_export_dialog_and_file(self):
        fields = self.make_jsonrpc_request('/web/export/get_fields', {'model': 'res.partner', 'domain': []})
        self.assertNotIn('email', [field['id'] for field in fields])
        self.assertIn('name', [field['id'] for field in fields])
        data = json.dumps({'model': 'res.partner', 'ids': self.partner.ids, 'domain': [], 'import_compat': False,
                           'fields': [{'name': 'name', 'label': 'Name'}, {'name': 'email', 'label': 'Email'}]})
        response = self.url_open('/web/export/csv', data={'data': data, 'csrf_token': self.csrf_token()})
        self.assertNotIn('secret@example.com', response.text)
        self.assertIn('does not allow using the field', response.text)

    def test_a_language_or_an_aggregate_does_not_hide_a_field(self):
        for method, args, kwargs in (
            ('export_data', [self.partner.ids, ['email@en_US']], {}),
            ('formatted_read_group', [[]], {'groupby': ['name'], 'aggregates': ['__count'],
                                            'having': [('email:count_distinct', '>', 0)]}),
            ('search_read', [[]], {'fields': ['name'], 'order': 'email:count_distinct'}),
        ):
            with self.subTest(method=method), self.assertRaises(JsonRpcException):
                self._rpc(f'/web/dataset/call_kw/res.partner/{method}', 'res.partner', method, args, kwargs)

    def test_values_read_for_a_grouped_relation_are_blanked(self):
        result = self._rpc('/web/dataset/call_kw/res.partner/web_read_group', 'res.partner', 'web_read_group',
                           [[('id', '=', self.child.id)], ['parent_id']],
                           {'groupby_read_specification': {'parent_id': {'email': {}}}})
        values = result['groups'][0]['__values']
        self.assertIs(values['email'], False)

    def test_read_only_fields_of_lines_are_not_written(self):
        self._rpc('/web/dataset/call_kw/res.partner/web_save', 'res.partner', 'web_save',
                  [self.partner.ids, {'child_ids': [[1, self.child.id, {'phone': '999', 'name': 'Renamed Child'}]]}],
                  {'specification': {}})
        self.child.invalidate_recordset()
        self.assertEqual((self.child.name, self.child.phone), ('Renamed Child', '222'))

    def test_block_export_takes_effect(self):
        self.assertTrue(self.user.with_user(self.user).env.user.has_group('base.group_allow_export'))
        self.profile.block_export = True
        self.assertFalse(self.env(user=self.user).user.has_group('base.group_allow_export'))

    def test_a_profile_that_denies_does_not_widen_the_union(self):
        # the class profile says nothing about contacts, so it would grant them all
        self.profile.user_ids = [(3, self.user.id)]
        Profile = self.env['om.access.profile']
        Profile.create({'name': 'No edit', 'user_ids': [(6, 0, self.user.ids)],
                        'model_ids': [(0, 0, {'model_id': self.partner_model.id, 'perm_write': False})]})
        Profile.create({'name': 'Edit mine', 'user_ids': [(6, 0, self.user.ids)],
                        'model_ids': [(0, 0, {'model_id': self.partner_model.id,
                                              'domain': "[('user_id', '=', uid)]"})]})
        with self.assertRaises(AccessError):
            self.partner.with_user(self.user).write({'name': 'Not mine'})

    def test_an_api_key_follows_the_sign_in_rules(self):
        key = self.env['res.users.apikeys'].with_user(self.user)._generate(
            'rpc', 'review', datetime.now() + timedelta(days=1))
        headers = {'Authorization': f'bearer {key}', 'X-Odoo-Database': self.env.cr.dbname}
        self.assertEqual(self.url_open('/json/2/res.partner/search_count', json={'domain': []},
                                       headers=headers).status_code, 200)
        self.profile.block_login = True
        self.assertNotEqual(self.url_open('/json/2/res.partner/search_count', json={'domain': []},
                                          headers=headers).status_code, 200)

    def test_xmlrpc_and_the_allowed_networks(self):
        from odoo.addons.om_user_audit.models.client_call import RPC_ADDRESS
        from odoo.exceptions import AccessDenied
        credential = {'login': self.user.login, 'password': self.password, 'type': 'password'}
        user = self.user.with_user(self.user)
        self.profile.allowed_ips = '127.0.0.1'
        # the address kept by the RPC controllers is checked
        token = RPC_ADDRESS.set('127.0.0.1')
        try:
            user._check_credentials(credential, {'interactive': False})
        finally:
            RPC_ADDRESS.reset(token)
        # an address Odoo does not know is refused, never let through
        with self.assertRaises(AccessDenied):
            user._check_credentials(credential, {'interactive': False})
        # end to end, the address read from the request
        self.assertEqual(self.xmlrpc_common.authenticate(self.env.cr.dbname, self.user.login, self.password, {}),
                         self.user.id)
        self.profile.allowed_ips = '10.0.0.0/8'
        self.assertFalse(self.xmlrpc_common.authenticate(self.env.cr.dbname, self.user.login, self.password, {}))

    def test_the_last_administrator_from_the_user_side(self):
        Profile = type(self.env['om.access.profile'])
        admins = self.env.ref('base.group_system').all_user_ids
        locked = self.env['om.access.profile'].create({'name': 'Locked', 'block_login': True,
                                                       'apply_to_admin': True})
        with patch.object(Profile, '_exempt_user_ids', lambda self: ()), self.assertRaises(ValidationError):
            admins.write({'access_profile_ids': [(4, locked.id)]})

    def test_users_cannot_read_the_access_of_others(self):
        other = new_test_user(self.env, 'om_access_review_other', groups='base.group_user')
        with self.assertRaises(AccessError):
            other.with_user(self.user).read(['access_effective'])

    def test_a_note_naming_partners_is_a_message(self):
        self.profile.hide_send_message_all = True
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/mail/message/post', {
                'thread_model': 'res.partner', 'thread_id': self.partner.id,
                'post_data': {'body': 'Hi', 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_note',
                              'partner_ids': [self.partner.id]}})
        with self.assertRaises(JsonRpcException):
            self._rpc('/web/dataset/call_kw/res.partner/message_post', 'res.partner', 'message_post',
                      [self.partner.ids], {'body': 'Hi', 'subtype_xmlid': 'mail.mt_comment'})
