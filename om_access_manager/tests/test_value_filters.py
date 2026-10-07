# Value filters of fields: combined across profiles like the rest, merged
# into the views, and checked when a client saves a record.
import xmlrpc.client

from odoo.tests import new_test_user, tagged

from odoo.addons.om_access_manager.models.value_filters import and_domains, or_domains

from .audit import HttpCase, JsonRpcException


@tagged('post_install', '-at_install')
class TestValueFilters(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-values-pw'
        cls.user = new_test_user(cls.env, 'om_access_values_user', groups='base.group_user,base.group_partner_manager',
                                 password=cls.password)
        cls.be, cls.fr, cls.de = (cls.env.ref(f'base.{code}') for code in ('be', 'fr', 'de'))
        cls.state_be = cls.env['res.country.state'].create({'name': 'Brabant', 'code': 'OMBR', 'country_id': cls.be.id})
        cls.state_fr = cls.env['res.country.state'].create({'name': 'Var', 'code': 'OMVA', 'country_id': cls.fr.id})
        cls.tag_a, cls.tag_b = cls.env['res.partner.category'].create([{'name': 'OM A'}, {'name': 'OM B'}])
        cls.partner = cls.env['res.partner'].create({'name': 'Filtered', 'country_id': cls.de.id})
        cls.profile_be = cls._profile('Belgium', [('country_id', [cls.be])])
        cls.profile_fr = cls._profile('France', [('country_id', [cls.fr])])

    @classmethod
    def _profile(cls, name, filters, **values):
        Fields = cls.env['ir.model.fields']
        model = cls.env['ir.model']._get('res.partner')
        return cls.env['om.access.profile'].create({
            'name': name,
            'field_ids': [
                (0, 0, {'model_id': model.id, 'field_id': Fields._get('res.partner', field_name).id,
                        'mode': 'keep', 'field_domain': repr([('id', 'in', [record.id for record in allowed])])
                        if isinstance(allowed, list) else allowed})
                for field_name, allowed in filters
            ],
            **values,
        })

    def setUp(self):
        super().setUp()
        self.authenticate(self.user.login, self.password)

    def _call(self, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {},
        })

    def _carry(self, *profiles):
        self.user.access_profile_ids = [(6, 0, [profile.id for profile in profiles])]

    def test_combining_expressions(self):
        # an implicit AND inside one filter stays together under the OR
        self.assertEqual(
            or_domains(["[('a', '=', 1), ('b', '=', 2)]", "[('c', '=', company_id)]"]),
            "['|', '&', ('a', '=', 1), ('b', '=', 2), ('c', '=', company_id)]")
        self.assertIsNone(or_domains(["[('a', '=', 1)]", "[]"]))
        self.assertIsNone(or_domains(["[('a', '=', 1)]", "context.get('d')"]))
        self.assertEqual(and_domains(["[('a', '=', 1)]", "[('c', '=', parent.x)]"]),
                         "[('a', '=', 1), ('c', '=', parent.x)]")
        self.assertEqual(and_domains(["context.get('d', [])", "[('a', '=', 1)]"]),
                         "(context.get('d', [])) + ([('a', '=', 1)])")

    def test_additive_profiles_widen_the_values(self):
        self._carry(self.profile_be, self.profile_fr)
        for country in (self.be, self.fr):
            self._call('res.partner', 'write', [self.partner.ids, {'country_id': country.id}])
            self.assertEqual(self.partner.country_id, country)
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'write', [self.partner.ids, {'country_id': self.de.id}])

    def test_an_additive_profile_without_a_filter_lifts_it(self):
        self._carry(self.profile_be, self.env['om.access.profile'].create({'name': 'No filter'}))
        self._call('res.partner', 'write', [self.partner.ids, {'country_id': self.fr.id}])
        self.assertEqual(self.partner.country_id, self.fr)

    def test_override_profiles_narrow_the_values(self):
        override = self._profile('Not France', [('country_id', "[('id', '!=', %d)]" % self.fr.id)],
                                 strictness='override')
        self._carry(self.profile_be, self.profile_fr, override)
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'write', [self.partner.ids, {'country_id': self.fr.id}])
        self._call('res.partner', 'write', [self.partner.ids, {'country_id': self.be.id}])
        self.assertEqual(self.partner.country_id, self.be)

    def test_creating_and_python_code(self):
        self._carry(self.profile_be)
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'create', [{'name': 'New', 'country_id': self.fr.id}])
        self._call('res.partner', 'create', [{'name': 'New', 'country_id': self.be.id}])
        # the value the record already holds is not judged; Python code is left alone
        self._call('res.partner', 'write', [self.partner.ids, {'name': 'Renamed', 'country_id': self.de.id}])
        self.partner.with_user(self.user).country_id = self.fr
        self.assertEqual(self.partner.country_id, self.fr)

    def test_filter_reading_the_record(self):
        self._carry(self._profile('Own states', [('state_id', "[('country_id', '=', country_id)]")]))
        self.partner.country_id = self.be
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'write', [self.partner.ids, {'state_id': self.state_fr.id}])
        # the country written with it counts
        self._call('res.partner', 'write', [self.partner.ids, {'state_id': self.state_fr.id,
                                                                  'country_id': self.fr.id}])
        self.assertEqual(self.partner.state_id, self.state_fr)

    def test_lines_and_many2many(self):
        self._carry(self._profile('Tag A', [('category_id', [self.tag_a])]))
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'write', [self.partner.ids, {'child_ids': [
                (0, 0, {'name': 'Line', 'category_id': [(6, 0, [self.tag_b.id])]}),
            ]}])
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'write', [self.partner.ids, {'category_id': [(4, self.tag_b.id)]}])
        self._call('res.partner', 'write', [self.partner.ids, {'category_id': [(4, self.tag_a.id)]}])
        self.assertEqual(self.partner.category_id, self.tag_a)

    def test_filter_reading_the_parent(self):
        self._carry(self._profile('Parent country', [('country_id', "[('id', '=', parent.country_id)]")]))
        self.partner.country_id = self.be
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'write', [self.partner.ids, {'child_ids': [
                (0, 0, {'name': 'Line', 'country_id': self.fr.id}),
            ]}])
        self._call('res.partner', 'write', [self.partner.ids, {'child_ids': [
            (0, 0, {'name': 'Line', 'country_id': self.be.id}),
        ]}])
        self.assertEqual(self.partner.child_ids.country_id, self.be)

    def test_xmlrpc(self):
        self._carry(self.profile_be)
        with self.assertRaises(xmlrpc.client.Fault):
            self.xmlrpc_object.execute_kw(
                self.env.cr.dbname, self.user.id, self.password, 'res.partner', 'write',
                [self.partner.ids, {'country_id': self.fr.id}])
        self.assertEqual(self.partner.country_id, self.de)

    def test_views_carry_the_combined_filter(self):
        self._carry(self.profile_be, self.profile_fr)
        arch = self.env['res.partner'].with_user(self.user).get_view(view_type='form')['arch']
        self.assertIn("['|', ('id', 'in', [%d]), ('id', 'in', [%d])]" % (self.be.id, self.fr.id), arch)

    def test_views_keep_the_domain_of_the_field(self):
        self._carry(self._profile('Own states', [('state_id', "[('code', '!=', 'X')]")]))
        arch = self.env['res.partner'].with_user(self.user).get_view(view_type='form')['arch']
        # the domain of the field itself (country_id =? country_id) is kept, not replaced
        self.assertIn("('country_id', '=?', country_id), ('code', '!=', 'X')", arch)

    def test_options_alone_reach_the_views(self):
        Fields = self.env['ir.model.fields']
        self._carry(self.env['om.access.profile'].create({'name': 'No link', 'field_ids': [(0, 0, {
            'model_id': self.env['ir.model']._get('res.partner').id,
            'field_id': Fields._get('res.partner', 'country_id').id, 'mode': 'keep', 'no_open': True,
        })]}))
        arch = self.env['res.partner'].with_user(self.user).get_view(view_type='form')['arch']
        self.assertRegex(arch, r'name="country_id"[^>]*no_open')
