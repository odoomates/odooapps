# Why can, or can't, a user do something; and the versions of a profile, their
# differences and their restore.
import json

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestExplain(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_access_explain_user', groups='base.group_user,base.group_partner_manager')
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.allowed, cls.other = cls.env['res.partner'].create([{'name': 'OM Allowed'}, {'name': 'OM Other'}])
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Explained Profile',
            'user_ids': [(6, 0, cls.user.ids)],
            'model_ids': [(0, 0, {'model_id': cls.partner_model.id, 'perm_unlink': False,
                                  'domain': "[('id', '=', %d)]" % cls.allowed.id})],
        })

    def _explain(self, model, operation, record=None, user=None):
        return self.env['om.access.explain'].create({
            'user_id': (user or self.user).id,
            'model_id': self.env['ir.model']._get(model).id,
            'operation': operation,
            'res_id': record.id if record else 0,
        })

    def test_odoo_itself_refuses(self):
        wizard = self._explain('ir.config_parameter', 'read')
        self.assertEqual(wizard.verdict, 'denied')
        self.assertIn('None of the groups of the user gives this right', wizard.report)

    def test_the_profile_refuses_an_operation(self):
        wizard = self._explain('res.partner', 'unlink')
        self.assertEqual(wizard.verdict, 'denied')
        self.assertIn('Explained Profile', wizard.report)
        self.assertIn('Together, the profiles refuse this operation', wizard.report)

    def test_record_filter_on_the_model_and_on_a_record(self):
        self.assertEqual(self._explain('res.partner', 'read').verdict, 'some')
        inside = self._explain('res.partner', 'read', self.allowed)
        self.assertEqual(inside.verdict, 'allowed')
        self.assertEqual(inside.record_name, 'OM Allowed')
        self.assertIn('among the ones the profiles leave', inside.report)
        outside = self._explain('res.partner', 'read', self.other)
        self.assertEqual(outside.verdict, 'denied')
        self.assertIn('outside the ones the profiles leave', outside.report)
        # the answer is the one of the real check
        self.assertFalse(self.other.with_user(self.user).has_access('read'))
        self.assertTrue(self.allowed.with_user(self.user).has_access('read'))

    def test_the_administrator_is_never_restricted(self):
        # Odoo's own company rules still apply to the administrator: check a record
        wizard = self._explain('res.partner', 'unlink', self.other, user=self.env.ref('base.user_admin'))
        self.assertEqual(wizard.verdict, 'allowed')
        self.assertIn('profiles never restrict them', wizard.report)

    def test_fields_and_refusals_are_listed(self):
        self.profile.write({'field_ids': [(0, 0, {
            'model_id': self.partner_model.id, 'mode': 'hide',
            'field_id': self.env['ir.model.fields']._get('res.partner', 'email').id})]})
        self.env['om.user.audit.log'].sudo().create({
            'event': 'refused', 'user_id': self.user.id, 'model': 'res.partner', 'res_id': self.other.id,
            'res_name': 'OM Other', 'method': 'unlink', 'detail': 'Refused for the test',
        })
        wizard = self._explain('res.partner', 'read')
        self.assertIn('Hidden: Email', wizard.report)
        self.assertIn('Refused for the test', wizard.report)

    def test_a_refusal_opens_its_question(self):
        log = self.env['om.user.audit.log'].sudo().create({
            'event': 'refused', 'user_id': self.user.id, 'model': 'res.partner', 'res_id': self.other.id,
            'method': 'unlink', 'detail': 'Refused',
        })
        values = self.env['om.access.explain'].with_context(
            active_model='om.user.audit.log', active_id=log.id).default_get(['user_id', 'model_id', 'operation', 'res_id'])
        self.assertEqual(values['user_id'], self.user.id)
        self.assertEqual(values['model_id'], self.partner_model.id)
        self.assertEqual(values['operation'], 'unlink')
        self.assertEqual(values['res_id'], self.other.id)


@tagged('post_install', '-at_install')
class TestVersions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_access_version_user', groups='base.group_user')
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.settings = cls.env.ref('base.menu_administration')

    def setUp(self):
        super().setUp()
        # save what the setup left pending: the tests count from there
        self.env.cr.precommit.run()

    def _commit(self):
        """ What a commit does for the versions, without committing. """
        self.env.flush_all()
        self.env.cr.precommit.run()

    def _versions(self, profile):
        return self.env['om.access.profile.version'].search([('profile_id', '=', profile.id)], order='number desc')

    def _profile(self):
        profile = self.env['om.access.profile'].create({
            'name': 'Versioned Profile',
            'user_ids': [(6, 0, self.user.ids)],
            'hidden_menu_ids': [(6, 0, self.settings.ids)],
        })
        self._commit()
        return profile

    def test_one_version_per_change_and_none_without(self):
        profile = self._profile()
        self.assertEqual(self._versions(profile).mapped('number'), [1])
        self.assertEqual(self._versions(profile).summary, 'First version')
        # several changes in one transaction make one version
        profile.write({'block_export': True})
        profile.write({'model_ids': [(0, 0, {'model_id': self.partner_model.id, 'perm_unlink': False})]})
        self._commit()
        self.assertEqual(self._versions(profile).mapped('number'), [2, 1])
        latest = self._versions(profile)[0]
        self.assertIn('Block Export', latest.summary)
        self.assertIn('Contact', latest.changes)
        self.assertIn('Added', latest.summary)
        # a write changing nothing makes no version
        profile.write({'block_export': True})
        self._commit()
        self.assertEqual(profile.version_count, 2)

    def test_a_line_change_shows_what_changed(self):
        profile = self._profile()
        profile.write({'model_ids': [(0, 0, {'model_id': self.partner_model.id})]})
        self._commit()
        profile.model_ids.perm_unlink = False
        self._commit()
        changes = self._versions(profile)[0].changes
        self.assertIn('Contact', changes)
        self.assertIn('Delete', changes)
        self.assertIn('Yes', changes)
        self.assertIn('No', changes)

    def test_restore_brings_back_a_version_and_keeps_the_users(self):
        profile = self._profile()
        first = self._versions(profile)
        other = new_test_user(self.env, 'om_access_version_other', groups='base.group_user')
        profile.write({
            'hidden_menu_ids': [(5,)], 'block_export': True,
            'model_ids': [(0, 0, {'model_id': self.partner_model.id, 'perm_unlink': False})],
            'user_ids': [(4, other.id)],
        })
        self._commit()
        self.assertIn('Settings', first.changes_since)
        self.assertFalse(first.is_current)
        first.action_restore()
        self._commit()
        self.assertEqual(profile.hidden_menu_ids, self.settings)
        self.assertFalse(profile.block_export)
        self.assertFalse(profile.model_ids)
        # the users are not part of a restore
        self.assertEqual(profile.user_ids, self.user | other)
        latest = self._versions(profile)[0]
        self.assertEqual(latest.number, 3)
        self.assertEqual(latest.restored_from_id, first)
        self.assertIn('Restored Version 1', ' '.join(profile.message_ids.mapped('body')))
        # restoring the version the profile is at is refused
        with self.assertRaises(UserError):
            latest.action_restore()

    def test_profiles_without_version_get_one(self):
        profile = self._profile()
        self._versions(profile).sudo().unlink()
        self.env['om.access.profile']._om_version_missing()
        self.assertEqual(profile.version_count, 1)

    def test_versions_are_read_only(self):
        manager = new_test_user(self.env, 'om_access_version_manager',
                                groups='base.group_user,om_access_manager.group_access_manager')
        version = self._versions(self._profile()).with_user(manager)
        self.assertTrue(version.data)
        with self.assertRaises(Exception):
            version.write({'summary': 'Rewritten'})
        with self.assertRaises(Exception):
            version.unlink()

    def test_sign_in_rules_travel(self):
        profile = self._profile()
        profile.write({
            'allowed_ips': '10.0.0.0/8', 'single_session': True,
            'login_slot_ids': [(0, 0, {'dayofweek': '0', 'hour_from': 8.0, 'hour_to': 17.0})],
        })
        data = json.loads(profile._om_export())['profiles'][0]
        self.assertEqual(data['allowed_ips'], '10.0.0.0/8')
        self.assertEqual(data['login_slots'], [{'dayofweek': '0', 'hour_from': 8.0, 'hour_to': 17.0}])
        copy = self.env['om.access.profile']._om_import(profile._om_export())
        self.assertEqual(copy.allowed_ips, '10.0.0.0/8')
        self.assertTrue(copy.single_session)
        self.assertEqual(copy.login_slot_ids.mapped('hour_to'), [17.0])
