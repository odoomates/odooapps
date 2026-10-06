# Who carries a profile: through an Odoo group, for a while, or copied from
# another user.
import json
from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestMembership(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_access_member_user', groups='base.group_user')
        cls.other = new_test_user(cls.env, 'om_access_member_other', groups='base.group_user')
        cls.group = cls.env['res.groups'].create({'name': 'OM Access Member Group'})
        cls.Profile = cls.env['om.access.profile']
        cls.profile = cls.Profile.create({'name': 'Members', 'hide_activities': True})

    def _rules(self, user):
        return self.Profile.with_user(user)._current_rules()

    def test_a_group_member_carries_the_profile(self):
        self.profile.group_ids = self.group
        self.assertFalse(self._rules(self.user).enabled)
        self.user.write({'groups_id': [(4, self.group.id)]})
        self.assertTrue(self._rules(self.user).has_flag('hide_activities'))
        self.assertIn(self.user, self.profile._om_members())
        self.user.write({'groups_id': [(3, self.group.id)]})
        self.assertFalse(self._rules(self.user).enabled)
        # from the group's side
        self.group.write({'users': [(4, self.other.id)]})
        self.assertTrue(self._rules(self.other).enabled)
        self.group.write({'users': [(3, self.other.id)]})
        self.assertFalse(self._rules(self.other).enabled)

    def test_a_group_implying_the_profile_group(self):
        self.profile.group_ids = self.group
        manager = self.env['res.groups'].create({'name': 'OM Access Manager Group',
                                                 'implied_ids': [(4, self.group.id)]})
        self.user.write({'groups_id': [(4, manager.id)]})
        self.assertTrue(self._rules(self.user).enabled)

    def test_the_group_of_a_profile_cannot_give_another(self):
        other = self.Profile.create({'name': 'Other'})
        with self.assertRaises(ValidationError):
            self.profile.group_ids = other.group_id

    def test_a_temporary_assignment_between_its_dates(self):
        today = date(2026, 3, 10)
        with freeze_time(today):
            line = self.env['om.access.profile.assignment'].create({
                'profile_id': self.profile.id, 'user_id': self.user.id,
                'date_from': today + timedelta(days=1), 'date_to': today + timedelta(days=2)})
            self.assertEqual(line.state, 'planned')
            self.assertFalse(self._rules(self.user).enabled)
        with freeze_time(today + timedelta(days=1)):
            self.env['om.access.profile.assignment']._cron_refresh()
            self.assertEqual(line.state, 'active')
            self.assertTrue(self._rules(self.user).enabled)
            # the menus are cached per group set: the user joins the profile's group
            self.assertIn(self.user, self.profile.group_id.users)
            self.assertEqual(self.profile.user_count, 1)
        with freeze_time(today + timedelta(days=3)):
            self.env['om.access.profile.assignment']._cron_refresh()
            self.assertEqual((line.state, line.active), ('ended', False))
            self.assertFalse(self._rules(self.user).enabled)
            self.assertNotIn(self.user, self.profile.group_id.users)
            self.assertIn(line, self.profile.assignment_ids)

    def test_an_assignment_cannot_end_before_it_starts(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.env['om.access.profile.assignment'].create({
                'profile_id': self.profile.id, 'user_id': self.user.id,
                'date_from': date(2026, 3, 10), 'date_to': date(2026, 3, 9)})

    def test_the_last_administrator_through_a_group(self):
        Profile = type(self.Profile)
        self.profile.write({'block_login': True, 'apply_to_admin': True})
        with patch.object(Profile, '_exempt_user_ids', lambda self: ()), self.assertRaises(ValidationError):
            self.profile.group_ids = self.env.ref('base.group_system')

    def test_copy_and_move_access(self):
        self.user.access_profile_ids = self.profile
        self.env['om.access.profile.assignment'].create({
            'profile_id': self.Profile.create({'name': 'Cover'}).id, 'user_id': self.user.id,
            'date_from': fields.Date.today(), 'note': 'leave'})
        Wizard = self.env['om.access.copy.access'].with_context(active_model='res.users', active_id=self.user.id)
        wizard = Wizard.create({'user_ids': [(6, 0, self.other.ids)]})
        self.assertEqual(wizard.source_user_id, self.user)
        wizard.action_apply()
        self.assertEqual(self.other.access_profile_ids, self.profile)
        self.assertEqual(self.other.access_assignment_ids.note, 'leave')
        self.assertTrue(self._rules(self.other).enabled)
        self.assertIn(self.other, self.profile.group_id.users)
        # a job change: the access moves
        third = new_test_user(self.env, 'om_access_member_third', groups='base.group_user')
        Wizard.create({'user_ids': [(6, 0, third.ids)], 'mode': 'move'}).action_apply()
        self.assertEqual(third.access_profile_ids, self.profile)
        self.assertFalse(self.user.access_profile_ids)
        self.assertFalse(self.user.access_assignment_ids)
        self.assertNotIn(self.user, self.profile.group_id.users)
        self.assertFalse(self._rules(self.user).enabled)

    def test_export_carries_groups_and_conditions(self):
        partner_model = self.env['ir.model']._get('res.partner')
        self.profile.write({
            'group_ids': [(6, 0, self.group.ids)],
            'field_ids': [(0, 0, {'model_id': partner_model.id, 'mode': 'hide', 'condition': "ref == 'vip'",
                                  'field_id': self.env['ir.model.fields']._get('res.partner', 'email').id})],
        })
        data = json.loads(self.profile._om_export())
        data['profiles'][0]['name'] = 'Imported Members'
        imported = self.Profile._om_import(json.dumps(data))
        self.assertEqual(imported.field_ids.condition, "ref == 'vip'")
        self.assertEqual(imported.group_ids, self.group)
