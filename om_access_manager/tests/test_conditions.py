# Rules that apply only to the records matching a condition.
from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException

from odoo.addons.om_access_manager.models.conditions import ConditionError, condition_domain


@tagged('post_install', '-at_install')
class TestConditions(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-condition-pw'
        cls.user = new_test_user(cls.env, 'om_access_condition_user',
                                 groups='base.group_user,base.group_partner_manager', password=cls.password)
        Fields = cls.env['ir.model.fields']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.company = cls.env['res.partner'].create({'name': 'Company', 'ref': 'vip',
                                                     'email': 'company@example.com', 'phone': '111'})
        cls.person = cls.env['res.partner'].create({'name': 'Person', 'email': 'person@example.com',
                                                    'phone': '222', 'ref': 'locked'})
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Conditions',
            'user_ids': [(6, 0, cls.user.ids)],
            'field_ids': [
                (0, 0, {'model_id': cls.partner_model.id, 'mode': 'hide', 'condition': "ref == 'vip'",
                        'field_id': Fields._get('res.partner', 'email').id}),
                (0, 0, {'model_id': cls.partner_model.id, 'mode': 'readonly', 'condition': "ref == 'locked'",
                        'field_id': Fields._get('res.partner', 'phone').id}),
            ],
            'button_ids': [(0, 0, {
                'model_id': cls.partner_model.id, 'button_type': 'object',
                'button_name': 'action_archive', 'mode': 'hide_block', 'condition': "ref == 'vip'",
            })],
        })

    def setUp(self):
        super().setUp()
        self.authenticate(self.user.login, self.password)

    def _call(self, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {},
        })

    def test_the_parser(self):
        Partner = self.env['res.partner']
        self.assertEqual(condition_domain("is_company and ref != 'x'", Partner),
                         ['&', ('is_company', '!=', False), ('ref', '!=', 'x')])
        self.assertEqual(condition_domain("not active or id in [1, 2]", Partner),
                         ['|', '!', ('active', '!=', False), ('id', 'in', [1, 2])])
        self.assertEqual(condition_domain("user_id == uid", Partner, 7), [('user_id', '=', 7)])
        for expression in ('name.lower()', 'nonexistent == 1', '1 < id < 5', 'id == ref', 'id ==', '__import__'):
            with self.subTest(expression=expression), self.assertRaises(ConditionError):
                condition_domain(expression, Partner)

    def test_a_wrong_condition_is_refused_when_saved(self):
        with self.assertRaises(ValidationError):
            self.profile.field_ids[0].condition = 'missing_field'
        element = self.env['om.access.profile.element'].create({
            'profile_id': self.profile.id, 'model_id': self.partner_model.id,
            'element_type': 'filter', 'element_name': 'type_company'})
        with self.assertRaises(ValidationError):
            element.condition = "ref == 'vip'"

    def test_the_views_carry_the_conditions(self):
        arch = etree.fromstring(self.env['res.partner'].with_user(self.user).get_view(view_type='form')['arch'])
        email = arch.xpath("//form/sheet//field[@name='email']")[0]
        self.assertIn("ref == 'vip'", email.get('invisible'))
        phone = arch.xpath("//form/sheet//field[@name='phone']")[0]
        self.assertIn("ref == 'locked'", phone.get('readonly'))
        # the fields the conditions read are loaded with the record
        self.assertTrue(arch.xpath("/form//field[@name='ref']"))

    def test_hidden_only_on_matching_records(self):
        rows = self._call('res.partner', 'read', [(self.company | self.person).ids, ['email']])
        emails = {row['id']: row['email'] for row in rows}
        self.assertEqual(emails, {self.company.id: False, self.person.id: 'person@example.com'})
        # filtering on it would tell the hidden values apart
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'search_count', [[('email', '=', 'company@example.com')]])

    def test_read_only_on_matching_records(self):
        self._call('res.partner', 'write', [(self.company | self.person).ids, {'phone': '999'}])
        self.assertEqual(self.company.phone, '999')
        self.assertEqual(self.person.phone, '222')
        # the rest of the values are written
        self._call('res.partner', 'web_save', [self.person.ids, {'phone': '999', 'comment': 'kept'}],
                   {'specification': {}})
        self.assertEqual(self.person.phone, '222')
        self.assertIn('kept', str(self.person.comment))

    def test_button_blocked_on_matching_records(self):
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/web/dataset/call_button', {
                'model': 'res.partner', 'method': 'action_archive', 'args': [self.company.ids], 'kwargs': {}})
        self.assertTrue(self.company.active)
        self.make_jsonrpc_request('/web/dataset/call_button', {
            'model': 'res.partner', 'method': 'action_archive', 'args': [self.person.ids], 'kwargs': {}})
        self.assertFalse(self.person.active)
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'action_archive', [(self.person | self.company).ids])
