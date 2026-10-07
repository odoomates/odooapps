# Hidden and read-only fields and blocked buttons on client calls (call_kw,
# XML-RPC); the same methods called from Python are left alone.
import xmlrpc.client

from odoo.tests import new_test_user, tagged

from .audit import HttpCase, JsonRpcException, lines_after_transaction


@tagged('post_install', '-at_install')
class TestFieldGuard(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-guard-pw'
        cls.user = new_test_user(cls.env, 'om_access_guard_user', groups='base.group_user,base.group_partner_manager',
                                 password=cls.password)
        Fields = cls.env['ir.model.fields']
        partner_model = cls.env['ir.model']._get('res.partner')
        cls.partner = cls.env['res.partner'].create({
            'name': 'Guarded', 'email': 'secret@example.com', 'phone': '111',
        })
        cls.child = cls.env['res.partner'].create({'name': 'Child', 'parent_id': cls.partner.id})
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Guard',
            'user_ids': [(6, 0, cls.user.ids)],
            'field_ids': [
                (0, 0, {'model_id': partner_model.id, 'field_id': Fields._get('res.partner', 'email').id,
                        'mode': 'hide'}),
                (0, 0, {'model_id': partner_model.id, 'field_id': Fields._get('res.partner', 'phone').id,
                        'mode': 'readonly'}),
            ],
            'button_ids': [(0, 0, {
                'model_id': partner_model.id, 'button_type': 'object',
                'button_name': 'action_archive', 'mode': 'block',
            })],
        })

    def setUp(self):
        super().setUp()
        self.authenticate(self.user.login, self.password)

    def _call(self, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {},
        })

    def test_a_hidden_file_is_not_served(self):
        # a tiny PNG
        image = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        self.partner.image_1920 = image
        url = f'/web/content?model=res.partner&id={self.partner.id}&field=image_1920'
        self.env['base'].flush()
        self.assertEqual(self.url_open(url).status_code, 200)
        self.profile.field_ids = [(0, 0, {
            'model_id': self.env['ir.model']._get('res.partner').id,
            'field_id': self.env['ir.model.fields']._get('res.partner', 'image_1920').id, 'mode': 'hide'})]
        self.env['base'].flush()
        self.assertNotEqual(self.url_open(url).status_code, 200)
        self.assertNotEqual(self.url_open(url + '&download=1').status_code, 200)

    def test_hidden_values_never_leave(self):
        result = self._call('res.partner', 'web_search_read', [], {
            'domain': [('id', '=', self.partner.id)],
            'fields': ['name', 'email'],
        })
        # blanked, not removed: the screens keep finding the field they expect
        self.assertEqual(result['records'][0]['name'], 'Guarded')
        self.assertIs(result['records'][0]['email'], False)
        rows = self._call('res.partner', 'read', [self.partner.ids, ['name', 'email']])
        self.assertIs(rows[0]['email'], False)
        # Odoo 19 lets a plain user read only some of the fields of a contact
        # (the call sessions, for one, are for administrators): name a handful
        rows = self._call('res.partner', 'read', [self.partner.ids, [
            'name', 'email', 'phone', 'street', 'city', 'comment', 'parent_id', 'category_id']])
        self.assertIs(rows[0]['email'], False)
        rows = self._call('res.partner', 'search_read', [[('id', '=', self.partner.id)], ['name', 'email', 'phone']])
        self.assertIs(rows[0]['email'], False)

    def test_hidden_values_never_leave_through_a_relation(self):
        # Odoo 15 gives the values of the lines of a one2many with the onchange
        result = self._call('res.partner', 'onchange', [[], {}, [], {
            'name': '', 'child_ids': '', 'child_ids.name': '', 'child_ids.email': ''}], {
            'context': {'default_child_ids': [(0, 0, {'name': 'Line', 'email': 'line@example.com'})]}})
        lines = [command[2] for command in result['value']['child_ids']
                 if len(command) > 2 and isinstance(command[2], dict)]
        self.assertEqual([line['name'] for line in lines], ['Line'])
        self.assertIs(lines[0]['email'], False)

    def test_hidden_fields_cannot_be_used_to_infer_them(self):
        attempts = [
            ('search_read', [[('email', 'ilike', 'secret')]], {'fields': ['name']}),
            ('search_count', [[('email', '=', 'secret@example.com')]], {}),
            ('search_read', [[('parent_id.email', 'ilike', 'secret')]], {'fields': ['name']}),
            ('search_read', [[('child_ids', 'any', [('parent_id.email', 'ilike', 'secret')])]], {}),
            ('search_read', [[]], {'fields': ['name'], 'order': 'email'}),
            ('read_group', [[], ['name'], ['email']], {}),
            ('web_read_group', [[], ['email'], ['email']], {}),
            ('export_data', [self.partner.ids, ['name', 'email']], {}),
        ]
        for method, args, kwargs in attempts:
            with self.subTest(method=method, args=args, kwargs=kwargs), self.assertRaises(JsonRpcException):
                self._call('res.partner', method, args, kwargs)

    def test_fields_get_leaves_hidden_fields_out(self):
        fields = self._call('res.partner', 'fields_get', [], {'attributes': ['string']})
        self.assertNotIn('email', fields)
        self.assertIn('name', fields)

    def test_read_only_and_hidden_fields_are_not_written(self):
        self._call('res.partner', 'write', [self.partner.ids, {
            'name': 'Renamed', 'phone': '999', 'email': 'changed@example.com'}])
        self._call('res.partner', 'write', [self.partner.ids, {'phone': '888'}])
        self.partner.invalidate_cache()
        self.assertEqual(self.partner.name, 'Renamed')
        self.assertEqual(self.partner.phone, '111')
        self.assertEqual(self.partner.email, 'secret@example.com')

    def test_python_code_is_left_alone(self):
        # the business code reading a hidden field as the user keeps working
        partner = self.partner.with_user(self.user)
        self.assertEqual(partner.email, 'secret@example.com')
        self.assertEqual(partner.read(['email'])[0]['email'], 'secret@example.com')
        self.assertIn('email', self.env['res.partner'].with_user(self.user).search_read(
            [('email', '=', 'secret@example.com')], ['email'])[0])

    def test_blocked_button_cannot_be_called_by_hand(self):
        with lines_after_transaction(self.env) as lines, self.assertRaises(JsonRpcException):
            self._call('res.partner', 'action_archive', [self.partner.ids])
        self.assertTrue(self.partner.active)
        # the refusal goes to the audit log, after the rollback of the request
        self.assertEqual([(line['event'], line['user_id'], line['model'], line['method'], line['record_ids'])
                          for line in lines],
                         [('refused', self.user.id, 'res.partner', 'action_archive', str(self.partner.id))])

    def test_xmlrpc(self):
        uid = self.user.id
        rows = self.xmlrpc_object.execute_kw(
            self.env.cr.dbname, uid, self.password, 'res.partner', 'read',
            [self.partner.ids], {'fields': ['name', 'email']})
        self.assertIs(rows[0]['email'], False)

    def test_blocked_button_through_xmlrpc(self):
        with self.assertRaises(xmlrpc.client.Fault):
            self.xmlrpc_object.execute_kw(
                self.env.cr.dbname, self.user.id, self.password, 'res.partner', 'action_archive',
                [self.partner.ids])
        self.assertTrue(self.partner.active)

    def test_api_key(self):
        # Odoo 15 has no JSON-2: an API key is used over XML-RPC
        key = self.env['res.users.apikeys'].with_user(self.user)._generate(
            'rpc', 'guard test')
        rows = self.xmlrpc_object.execute_kw(
            self.env.cr.dbname, self.user.id, key, 'res.partner', 'read',
            [self.partner.ids], {'fields': ['name', 'email']})
        self.assertIs(rows[0]['email'], False)
        with self.assertRaises(xmlrpc.client.Fault):
            self.xmlrpc_object.execute_kw(
                self.env.cr.dbname, self.user.id, key, 'res.partner', 'action_archive', [self.partner.ids])
        self.assertTrue(self.partner.active)

    def test_search_filters_on_a_hidden_field_go_with_it(self):
        from lxml import etree
        arch = etree.fromstring("""<search>
            <filter name="with_email" domain="[('email', '!=', False)]"/>
            <filter name="by_email" context="{'group_by': 'email'}"/>
            <filter name="parent_email" domain="[('email.x', '=', 1)]"/>
            <filter name="kept" domain="[('name', '!=', False), ('email_normalized', '!=', False)]"/>
        </search>""")
        Profile = self.env['om.access.profile'].with_user(self.user)
        Profile._apply_view_rules(Profile._current_rules(), arch, 'res.partner', 'search')
        self.assertEqual([node.get('name') for node in arch.iter('filter')], ['kept'])
