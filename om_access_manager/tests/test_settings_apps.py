# The apps of the Settings: removed from the screen, and what only they hold is
# not saved from a client.
from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.om_access_manager.models.om_access_profile_element import settings_app

from .audit import HttpCase


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
                    <div class="app_settings_block" data-string="OM Test" string="OM Test" data-key="om_test">
                        <field name="show_effect"/>
                        <div attrs="{'invisible': [('auth_signup_reset_password', '=', False)]}"/>
                    </div>
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
        # Odoo 16: an app of the Settings is a <div class="app_settings_block" data-key="...">
        return [settings_app(node) for node in etree.fromstring(arch).iter('div') if settings_app(node)]

    def test_the_hidden_app_leaves_the_settings(self):
        apps = self._apps(self.user)
        self.assertNotIn('general_settings', apps)
        self.assertIn('om_test', apps)
        self.assertIn('general_settings', self._apps(self.env.ref('base.user_admin')))

    def test_only_what_the_hidden_app_alone_holds_is_hidden(self):
        hidden = self.env['om.access.profile']._om_settings_fields({'general_settings'})
        self.assertIn('external_email_server_default', hidden)
        self.assertNotIn('show_effect', hidden, "shown by another app too")
        self.assertNotIn('auth_signup_reset_password', hidden, "read by another app")
        self.assertNotIn('is_root_company', hidden, "outside of every app")

    def test_a_client_cannot_save_what_the_hidden_app_holds(self):
        # Odoo 16 has no app name in its General Settings: the custom email servers
        self.env['ir.config_parameter'].set_param('base_setup.default_external_email_server', True)
        self.authenticate(self.user.login, self.password)
        fields = self._call('fields_get', [])
        self.assertNotIn('external_email_server_default', fields)
        self.assertIn('show_effect', fields)
        # Odoo 16 saves the Settings with create
        settings = self.env['res.config.settings'].browse(
            self._call('create', [{'external_email_server_default': False, 'show_effect': False}]))
        self.assertTrue(settings.external_email_server_default)
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

    def test_the_health_check_finds_the_apps_of_the_settings(self):
        self.assertFalse(self.profile._om_health_unmatched())
        self.profile.element_ids = [(0, 0, {
            'model_id': self.settings_model.id, 'element_type': 'settings', 'element_name': 'om_gone',
        })]
        self.assertEqual(len(self.profile._om_health_unmatched()), 1)

    def test_a_settings_app_rule_belongs_to_the_settings(self):
        with self.assertRaises(ValidationError):
            self.profile.element_ids = [(0, 0, {
                'model_id': self.env['ir.model']._get('res.partner').id, 'element_type': 'settings',
                'element_name': 'general_settings',
            })]
