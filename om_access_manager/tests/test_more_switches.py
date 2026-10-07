# The search bar and form switches, the apps, the fields kept out of exports,
# and the date presets, through the routes a client uses.
import json

from odoo.exceptions import AccessError
from odoo import http
from odoo.tests import new_test_user, tagged

from .audit import HttpCase, JsonRpcException


@tagged('post_install', '-at_install')
class TestMoreSwitches(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-switches-pw'
        cls.user = new_test_user(cls.env, 'om_access_switches', password=cls.password,
                                 groups='base.group_user,base.group_partner_manager,base.group_allow_export')
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'More Switches', 'user_ids': [(6, 0, cls.user.ids)]})
        cls.partner = cls.env['res.partner'].create({'name': 'Exported', 'email': 'secret@example.com'})

    def _call(self, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}})

    def test_the_search_bar_switches_reach_the_web_client(self):
        self.profile.write({'block_custom_filter': True, 'block_favorites': True})
        self.authenticate(self.user.login, self.password)
        page = self.url_open('/web').text
        self.assertIn('o_om_no_custom_filter', page)
        self.assertIn('o_om_no_favorites', page)
        self.assertNotIn('o_om_no_custom_group', page)

    def test_saving_a_search_is_refused(self):
        self.authenticate(self.user.login, self.password)
        # Odoo 15 saves a search with create_or_replace, for one user
        values = {'name': 'Mine', 'model_id': 'res.partner', 'domain': '[]', 'user_id': self.user.id}
        self._call('ir.filters', 'create_or_replace', [values])
        self.profile.block_favorites = True
        with self.assertRaises(JsonRpcException):
            self._call('ir.filters', 'create_or_replace', [dict(values, name='Another')])

    def test_changing_properties_is_refused(self):
        if 'properties' not in self.env['res.partner']._fields:
            self.skipTest("Odoo 15 contacts have no properties")
        self.profile.block_properties = True
        definition = [{'name': 'om_prop', 'string': 'Prop', 'type': 'char', 'definition_changed': True}]
        partner = self.partner.with_user(self.user)
        with self.assertRaises(AccessError):
            partner.write({'properties': definition})
        with self.assertRaises(AccessError):
            self.env['properties.base.definition'].with_user(self.user).browse().write(
                {'properties_definition': []})
        # setting the value of a property already defined stays allowed
        partner.write({'name': 'Renamed'})

    def test_installing_apps_is_refused(self):
        admin = new_test_user(self.env, 'om_access_apps_admin', groups='base.group_system')
        self.env['om.access.profile'].create({
            'name': 'No Apps', 'block_apps': True, 'apply_to_admin': True, 'user_ids': [(6, 0, admin.ids)]})
        module = self.env['ir.module.module'].search([('state', '=', 'uninstalled')], limit=1)
        with self.assertRaises(AccessError):
            module.with_user(admin).button_install()
        self.assertEqual(module.state, 'uninstalled')

    def test_a_field_kept_out_of_the_exports(self):
        self.env['om.access.profile.field'].create({
            'profile_id': self.profile.id, 'model_id': self.env['ir.model']._get('res.partner').id,
            'field_id': self.env['ir.model.fields']._get('res.partner', 'email').id,
            'mode': 'keep', 'no_export': True})
        self.authenticate(self.user.login, self.password)
        found = self.make_jsonrpc_request('/web/export/get_fields', {
            'model': 'res.partner', 'import_compat': False})
        self.assertNotIn('email', [field['id'] for field in found])
        self.assertIn('name', [field['id'] for field in found])
        # still shown on the screens
        rows = self._call('res.partner', 'read', [self.partner.ids, ['email']])
        self.assertEqual(rows[0]['email'], 'secret@example.com')
        data = json.dumps({'model': 'res.partner', 'ids': self.partner.ids, 'domain': [], 'import_compat': False,
                           'fields': [{'name': 'email', 'label': 'Email'}]})
        response = self.url_open('/web/export/csv', data={'data': data, 'csrf_token': http.WebRequest.csrf_token(self)})
        self.assertNotIn('secret@example.com', response.text)

    def test_date_presets(self):
        presets = self.env['om.access.profile.model']._preset_domains('res.partner')
        self.assertEqual(presets['month'], (
            'domain', "[('create_date', '>=', (context_today().replace(day=1)).strftime('%Y-%m-%d'))]"))
        line = self.env['om.access.profile.model'].create({
            'profile_id': self.profile.id, 'model_id': self.env['ir.model']._get('res.partner').id,
            'domain': presets['month'][1]})
        old = self.env['res.partner'].create({'name': 'Old'})
        self.env.cr.execute("UPDATE res_partner SET create_date = now() - interval '400 days' WHERE id = %s",
                            [old.id])
        self.env['base'].invalidate_cache()
        found = self.env['res.partner'].with_user(self.user).search([('id', 'in', (old | self.partner).ids)])
        self.assertEqual(found, self.partner)
        self.assertTrue(line)
