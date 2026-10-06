# The Restrict an App wizard, driven through Form so the onchanges run as in
# the browser.
from odoo.tests import Form, TransactionCase, new_test_user, tagged

from .audit import has_access


@tagged('post_install', '-at_install')
class TestAppWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_access_app_user', groups='base.group_user')
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'App Profile', 'user_ids': [(6, 0, cls.user.ids)],
        })
        cls.discuss = cls.env.ref('mail.menu_root_discuss')
        # Odoo 17 has no data menu under Discuss: give it its canned responses
        cls.env['ir.ui.menu'].create({
            'name': 'Canned Responses', 'parent_id': cls.discuss.id,
            'action': f"ir.actions.act_window,{cls.env.ref('mail.mail_shortcode_action').id}"})
        cls.settings = cls.env.ref('base.menu_administration')

    def _wizard(self, app, level=None, own_records=None):
        form = Form(self.env['om.access.app.wizard'].with_context(
            active_model='om.access.profile', active_id=self.profile.id))
        form.app_id = app
        if level:
            form.level = level
        if own_records is not None:
            form.own_records = own_records
        return form

    def _apply(self, app, level=None, **kwargs):
        wizard = self._wizard(app, level, **kwargs).save()
        wizard.action_apply()
        return wizard

    def _model_line(self, wizard, model_name):
        return wizard.model_line_ids.filtered(lambda line: line.model_id.model == model_name)

    def test_the_wizard_lists_what_the_app_brings(self):
        wizard = self._wizard(self.discuss).save()
        self.assertEqual(wizard.menu_line_ids[:1].menu_id, self.discuss)
        line = self._model_line(wizard, 'mail.shortcode')
        self.assertTrue(line.owned)
        self.assertTrue(line.perm_read and line.perm_unlink)

    def test_no_access_hides_the_app_and_refuses_its_data(self):
        self._apply(self.discuss, 'none')
        self.assertIn(self.discuss, self.profile.hidden_menu_ids)
        # only the app itself is stored: it hides everything below it
        self.assertFalse(self.profile.hidden_menu_ids - self.discuss)
        row = self.profile.model_ids.filtered(lambda row: row.model_id.model == 'mail.shortcode')
        self.assertFalse(row.perm_read or row.perm_create or row.perm_write or row.perm_unlink)
        self.assertFalse(has_access(self.env['mail.shortcode'].with_user(self.user).browse(), 'read'))

    def test_read_only_level(self):
        self._apply(self.discuss, 'readonly')
        Channel = self.env['mail.shortcode'].with_user(self.user).browse()
        self.assertTrue(has_access(Channel, 'read'))
        for operation in ('create', 'write', 'unlink'):
            self.assertFalse(has_access(Channel, operation), operation)

    def test_reopening_shows_the_profile_as_saved(self):
        self._apply(self.discuss, 'none')
        wizard = self._wizard(self.discuss).save()
        self.assertEqual(wizard.level, 'current')
        self.assertFalse(any(wizard.menu_line_ids.mapped('visible')))
        self.assertFalse(self._model_line(wizard, 'mail.shortcode').perm_read)

    def test_applying_twice_changes_nothing(self):
        def state():
            rows = self.profile.model_ids.read(
                ['model_id', 'perm_read', 'perm_create', 'perm_write', 'perm_unlink', 'domain'])
            return (self.profile.hidden_menu_ids,
                    sorted((tuple((key, value) for key, value in row.items() if key != 'id') for row in rows)))
        self._apply(self.discuss, 'readonly')
        before = state()
        self._apply(self.discuss)
        self.assertEqual(before, state())

    def test_full_access_cleans_the_profile_up(self):
        self._apply(self.discuss, 'none')
        self._apply(self.discuss, 'full')
        self.assertFalse(self.profile.hidden_menu_ids)
        self.assertFalse(self.profile.model_ids)

    def test_shared_data_is_left_alone(self):
        # the Settings app is built on the framework: none of its data is its own
        wizard = self._apply(self.settings, 'none')
        self.assertTrue(wizard.model_line_ids)
        self.assertFalse(wizard.model_line_ids.filtered('owned'))
        self.assertFalse(self.profile.model_ids)
        self.assertIn(self.settings, self.profile.hidden_menu_ids)

    def test_other_apps_are_left_alone(self):
        self._apply(self.settings, 'none')
        self._apply(self.discuss, 'full')
        self.assertIn(self.settings, self.profile.hidden_menu_ids)

    def test_own_records_and_hidden_actions(self):
        # an app of our own, on data with a salesperson and an Action menu entry
        partner_model = self.env['ir.model']._get('res.partner')
        action = self.env['ir.actions.act_window'].create({
            'name': 'Test Partners', 'res_model': 'res.partner',
        })
        app = self.env['ir.ui.menu'].create({'name': 'Test App'})
        self.env['ir.ui.menu'].create({
            'name': 'Partners', 'parent_id': app.id, 'action': f'ir.actions.act_window,{action.id}',
        })
        bound = self.env['ir.actions.server'].create({
            'name': 'Test Bound Action', 'model_id': partner_model.id, 'state': 'code', 'code': '',
            'binding_model_id': partner_model.id,
        })
        form = self._wizard(app)
        with form.model_line_ids.edit(0) as line:
            self.assertEqual(line.owner_field, 'user_id')
            line.scope = 'own'
        wizard = form.save()
        line = wizard.action_line_ids.filtered(lambda line: line.action_ref == bound)
        self.assertEqual(len(line), 1)
        line.visible = False
        wizard.action_apply()
        row = self.profile.model_ids.filtered(lambda row: row.model_id.model == 'res.partner')
        self.assertEqual(row.domain, "[('user_id', '=', uid)]")
        self.assertIn(bound.id, self.profile.hidden_action_ids.ids)
        bindings = self.env['ir.actions.actions'].with_user(self.user).get_bindings('res.partner')
        self.assertNotIn(bound.id, [entry['id'] for entry in bindings.get('action', [])])
