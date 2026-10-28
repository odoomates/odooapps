# The apps of the Settings: removed from the screen, and what only they hold is
# not saved from a client.
from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSettingsApps(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-settings-pw'
        cls.user = new_test_user(
            cls.env, 'om_access_settings_user', groups='base.group_user,base.group_system',
            password=cls.password)
        # a second app sharing a field with General Settings and reading another one
        cls.env['ir.ui.view'].create({
            'name': 'om_access_manager test: a second settings app',
            'model': 'res.config.settings',
            'inherit_id': cls.env.ref('base.res_config_settings_view_form').id,
            'arch': """
                <xpath expr="//form" position="inside">
                    <app string="OM Test" name="om_test">
                        <field name="show_effect"/>
                        <div invisible="not auth_signup_reset_password"/>
                    </app>
                </xpath>""",
        })
        cls.settings_model = cls.env['ir.model']._get('res.config.settings')
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'No General Settings',
            'user_ids': [(6, 0, cls.user.ids)],
            'apply_to_admin': True,
            'element_ids': [(0, 0, {
                'model_id': cls.settings_model.id, 'element_type': 'settings',
                'element_name': 'general_settings', 'element_label': 'General Settings',
            })],
        })

    def _call(self, method, args, kwargs=None):
        return self.make_jsonrpc_request(f'/web/dataset/call_kw/res.config.settings/{method}', {
            'model': 'res.config.settings', 'method': method, 'args': args, 'kwargs': kwargs or {},
        })

    def _apps(self, user):
        arch = self.env['res.config.settings'].with_user(user).get_view(view_type='form')['arch']
        return [node.get('name') for node in etree.fromstring(arch).iter('app')]

    def test_the_hidden_app_leaves_the_settings(self):
        apps = self._apps(self.user)
        self.assertNotIn('general_settings', apps)
        self.assertIn('om_test', apps)
        self.assertIn('general_settings', self._apps(self.env.ref('base.user_admin')))

    def test_only_what_the_hidden_app_alone_holds_is_hidden(self):
        hidden = self.env['om.access.profile']._om_settings_fields({'general_settings'})
        self.assertIn('web_app_name', hidden)
        self.assertNotIn('show_effect', hidden, "shown by another app too")
        self.assertNotIn('auth_signup_reset_password', hidden, "read by another app")
        self.assertNotIn('is_root_company', hidden, "outside of every app")

    def test_a_client_cannot_save_what_the_hidden_app_holds(self):
        self.env['ir.config_parameter'].set_param('web.web_app_name', 'Before')
        self.authenticate(self.user.login, self.password)
        fields = self._call('fields_get', [])
        self.assertNotIn('web_app_name', fields)
        self.assertIn('show_effect', fields)
        result = self._call('web_save', [[]], {
            'vals': {'web_app_name': 'After', 'show_effect': False}, 'specification': {}})
        settings = self.env['res.config.settings'].browse(result[0]['id'])
        self.assertEqual(settings.web_app_name, 'Before')
        self.assertFalse(settings.show_effect)

    def test_settings_users_only_with_apply_to_settings_users(self):
        self.profile.apply_to_admin = False
        self.assertIn('general_settings', self._apps(self.user))

    def test_the_panel_offers_the_apps_of_the_settings(self):
        menu = self.env.ref('base_setup.menu_config')
        panel = self.profile.om_menu_panel(menu.id)
        apps = {element['element_name']: element for element in panel['elements']
                if element['element_type'] == 'settings'}
        self.assertTrue(apps['general_settings']['hidden'])
        self.assertFalse(apps['om_test']['hidden'])
        self.profile.om_menu_panel_set(menu.id, {
            'kind': 'element', 'element_type': 'settings', 'element_name': 'om_test', 'label': 'OM Test',
            'hidden': True,
        })
        self.assertNotIn('om_test', self._apps(self.user))

    def test_a_settings_app_rule_belongs_to_the_settings(self):
        with self.assertRaises(ValidationError):
            self.profile.element_ids = [(0, 0, {
                'model_id': self.env['ir.model']._get('res.partner').id, 'element_type': 'settings',
                'element_name': 'general_settings',
            })]
