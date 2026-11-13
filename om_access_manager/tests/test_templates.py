# The ready-made profiles: the app-agnostic recipes, plus a test recipe for the
# parts that must be skipped and reported.
from odoo.tests import Form, TransactionCase, new_test_user, tagged

from odoo.addons.om_access_manager.models.om_access_templates import TEMPLATES, TEMPLATES_BY_KEY


@tagged('post_install', '-at_install')
class TestTemplates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_access_template_user', groups='base.group_user')
        cls.discuss = cls.env.ref('mail.menu_root_discuss')

    def _create(self, key, **values):
        form = Form(self.env['om.access.template.wizard'])
        form.template_key = key
        for name, value in values.items():
            setattr(form, name, value)
        action = form.save().action_create()
        return self.env['om.access.profile'].browse(action['res_id'])

    def _add_recipe(self, recipe):
        TEMPLATES.append(recipe)
        TEMPLATES_BY_KEY[recipe['key']] = recipe
        self.addCleanup(TEMPLATES.remove, recipe)
        self.addCleanup(TEMPLATES_BY_KEY.pop, recipe['key'])

    def test_only_the_templates_of_installed_apps_are_offered(self):
        installed = self.env['ir.module.module']._installed()
        offered = {key for key, _label in self.env['om.access.template.wizard']._selection_templates()}
        self.assertTrue({'auditor', 'app_user', 'app_readonly'} <= offered)
        for template in TEMPLATES:
            expected = all(module in installed for module in template['requires'])
            self.assertEqual(template['key'] in offered, expected, template['key'])

    def test_auditor(self):
        profile = self._create('auditor', user_ids=self.user)
        self.assertEqual(profile.name, 'Auditor')
        self.assertTrue(profile.global_readonly and profile.block_export and profile.block_import)
        self.assertIn('Created from the template Auditor', profile.note)
        Partner = self.env['res.partner'].with_user(self.user).browse()
        self.assertTrue(Partner.has_access('read'))
        self.assertFalse(Partner.has_access('write'))

    def test_a_template_for_any_app(self):
        profile = self._create('app_readonly', app_id=self.discuss, user_ids=self.user)
        self.assertEqual(profile.name, 'Discuss: App Read Only')
        Channel = self.env['discuss.channel'].with_user(self.user).browse()
        self.assertTrue(Channel.has_access('read'))
        self.assertFalse(Channel.has_access('write'))

    def test_missing_parts_are_skipped_and_reported(self):
        self._add_recipe({
            'key': 'om_test_recipe',
            'name': 'Test Recipe',
            'description': 'A recipe of the tests.',
            'requires': [],
            'apps': [
                {'app': 'mail.menu_root_discuss', 'level': 'none'},
                {'app': 'om_not_installed.menu_root', 'level': 'user', 'optional': True},
            ],
            'hide_menus': ['base.menu_administration', 'om_not_installed.menu_other'],
            'fields': [('res.partner', 'email', 'hide'), ('res.partner', 'om_no_such_field', 'hide'),
                       ('om.no.such.model', 'name', 'hide')],
            'switches': {'block_export': True},
        })
        profile = self._create('om_test_recipe')
        self.assertTrue(profile.block_export)
        self.assertEqual(profile.hidden_menu_ids, self.discuss | self.env.ref('base.menu_administration'))
        self.assertEqual(profile.field_ids.field_id.name, 'email')
        self.assertIn('om_not_installed is not installed', profile.note)
        self.assertIn('om_no_such_field', profile.note)
        # what is not installed at all is no news: the model of an absent app
        self.assertNotIn('om.no.such.model', profile.note)
        self.assertNotIn('menu_other', profile.note)

    def test_the_profile_stays_an_ordinary_one(self):
        profile = self._create('app_user', app_id=self.discuss)
        profile.model_ids.unlink()
        profile.hidden_menu_ids = False
        self.assertFalse(profile.model_ids or profile.hidden_menu_ids)
