# The history of a profile, the effective access on the user form, and the
# export and import of profiles.
import json

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHistoryAndTransfer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_access_transfer_user', groups='base.group_user')
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.settings = cls.env.ref('base.menu_administration')
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Transfer Profile',
            'block_export': True,
            'hide_costs': True,
            'user_ids': [(6, 0, cls.user.ids)],
            'hidden_menu_ids': [(6, 0, cls.settings.ids)],
            'model_ids': [(0, 0, {'model_id': cls.partner_model.id, 'perm_unlink': False,
                                  'domain': "[('user_id', '=', user.id)]"})],
            'field_ids': [(0, 0, {'model_id': cls.partner_model.id, 'mode': 'hide',
                                  'field_id': cls.env['ir.model.fields']._get('res.partner', 'email').id})],
        })

    def _notes(self, profile):
        return ' '.join(profile.message_ids.mapped('body'))

    def test_line_changes_are_logged(self):
        line = self.profile.model_ids
        line.perm_create = False
        line.unlink()
        notes = self._notes(self.profile)
        self.assertIn('Added', notes)
        self.assertIn('Changed', notes)
        self.assertIn('Removed', notes)
        self.assertIn(self.partner_model.name, notes)

    def test_switch_changes_are_tracked(self):
        # Odoo 19 tracks the changes of a record that existed before them:
        # end the creation first, as a commit would
        self.env.cr.precommit.run()
        self.profile.block_login = True
        # tracking is written when the transaction commits, which a test never does
        self.env.cr.precommit.run()
        # Odoo 19 keeps the tracked changes as tracking values of the message
        self.profile.invalidate_recordset(['message_ids'])
        tracked = self.profile.message_ids.tracking_value_ids.field_id.mapped('name')
        self.assertIn('block_login', tracked)

    def test_effective_access_on_the_user_form(self):
        self.assertIn('Transfer Profile', self.user.access_effective)
        self.assertIn('res.partner', self.user.access_effective)

    def test_export_and_import_round_trip(self):
        content = self.profile._om_export(with_users=True)
        data = json.loads(content)
        self.assertEqual(data['profiles'][0]['hidden_menus'][0]['xmlid'], 'base.menu_administration')
        self.assertEqual(data['profiles'][0]['users'], [self.user.login])
        copy = self.env['om.access.profile']._om_import(content, with_users=True)
        self.assertEqual(copy.name, 'Transfer Profile (imported)')
        self.assertTrue(copy.block_export and copy.hide_costs)
        self.assertEqual(copy.hidden_menu_ids, self.settings)
        self.assertEqual(copy.model_ids.model, 'res.partner')
        self.assertFalse(copy.model_ids.perm_unlink)
        self.assertEqual(copy.model_ids.domain, "[('user_id', '=', user.id)]")
        self.assertEqual(copy.field_ids.field_id.name, 'email')
        self.assertEqual(copy.user_ids, self.user)
        # replacing overwrites the profile of the same name instead
        self.profile.model_ids.unlink()
        again = self.env['om.access.profile']._om_import(content, replace=True)
        self.assertEqual(again, self.profile)
        self.assertEqual(self.profile.model_ids.model, 'res.partner')

    def test_what_this_database_lacks_is_reported(self):
        data = json.loads(self.profile._om_export())
        profile = data['profiles'][0]
        profile['name'] = 'From Elsewhere'
        profile['hidden_menus'].append({'xmlid': 'om_not_installed.menu', 'name': 'Nowhere'})
        profile['models'].append({'model': 'om.not.installed', 'perm_read': False})
        profile['fields'].append({'model': 'res.partner', 'field': 'om_no_field', 'mode': 'hide'})
        imported = self.env['om.access.profile']._om_import(json.dumps(data))
        notes = self._notes(imported)
        self.assertIn('om_not_installed.menu', notes)
        self.assertIn('om.not.installed', notes)
        self.assertIn('om_no_field', notes)
        self.assertEqual(imported.hidden_menu_ids, self.settings)

    def test_a_wrong_file_is_refused(self):
        for content in ('not json', json.dumps({'format': 'other'}),
                        json.dumps({'format': 'om_access_manager', 'version': 99})):
            with self.assertRaises(UserError):
                self.env['om.access.profile']._om_import(content)
