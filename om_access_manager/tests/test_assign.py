# Giving profiles to users: several at once from the Users list, and to every
# new internal user.
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from .audit import has_access


@tagged('post_install', '-at_install')
class TestAssign(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Profile = cls.env['om.access.profile']
        cls.sales = Profile.create({'name': 'Sales Staff'})
        cls.readonly = Profile.create({'name': 'Read Only', 'global_readonly': True})
        cls.users = (new_test_user(cls.env, 'om_access_assign_1', groups='base.group_user')
                     | new_test_user(cls.env, 'om_access_assign_2', groups='base.group_user'))

    def _assign(self, mode, profiles):
        wizard = self.env['om.access.assign'].with_context(
            active_model='res.users', active_ids=self.users.ids,
        ).create({'mode': mode, 'profile_ids': [(6, 0, profiles.ids)]})
        self.assertEqual(wizard.user_ids, self.users)
        wizard.action_apply()

    def test_add_remove_and_replace(self):
        self._assign('add', self.sales)
        self._assign('add', self.readonly)
        for user in self.users:
            self.assertEqual(user.access_profile_ids, self.sales | self.readonly)
        self._assign('remove', self.readonly)
        for user in self.users:
            self.assertEqual(user.access_profile_ids, self.sales)
        self._assign('replace', self.readonly)
        for user in self.users:
            self.assertEqual(user.access_profile_ids, self.readonly)
        self._assign('replace', self.env['om.access.profile'])
        self.assertFalse(self.users.access_profile_ids)

    def test_assigning_applies_the_profile(self):
        self._assign('add', self.readonly)
        Partner = self.env['res.partner'].with_user(self.users[0]).browse()
        self.assertFalse(has_access(Partner, 'write'))

    def test_add_needs_profiles(self):
        with self.assertRaises(UserError):
            self._assign('add', self.env['om.access.profile'])

    def test_new_internal_users_get_the_default_profiles(self):
        self.sales.for_new_users = True
        user = new_test_user(self.env, 'om_access_new_internal', groups='base.group_user')
        self.assertEqual(user.access_profile_ids, self.sales)
        portal = new_test_user(self.env, 'om_access_new_portal', groups='base.group_portal')
        self.assertFalse(portal.access_profile_ids)

    def test_users_can_be_searched_by_profile(self):
        self._assign('add', self.sales)
        Users = self.env['res.users']
        self.assertEqual(Users.search([('access_profile_ids', '=', self.sales.id)]), self.users)
        self.assertNotIn(self.users[0], Users.search([('access_profile_ids', '=', False)]))
