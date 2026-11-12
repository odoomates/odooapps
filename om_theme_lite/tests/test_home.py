from odoo.tests import TransactionCase, tagged

from ..models.res_users import LAUNCHER_ACTION
from ..hooks import post_init_hook, uninstall_hook


@tagged('post_install', '-at_install')
class TestHomeAction(TransactionCase):
    """The launcher is the home screen, without anything to switch on."""

    def setUp(self):
        super().setUp()
        self.action = self.env.ref(LAUNCHER_ACTION)

    def test_a_new_user_lands_on_the_launcher(self):
        user = self.env['res.users'].create({'name': 'Newcomer', 'login': 'om_newcomer'})
        self.assertEqual(user.action_id.id, self.action.id)

    def test_a_user_may_still_choose_their_own_home_action(self):
        own = self.env.ref('base.action_res_users')
        user = self.env['res.users'].create({
            'name': 'Opinionated', 'login': 'om_opinionated', 'action_id': own.id,
        })
        self.assertEqual(user.action_id.id, own.id)

    def test_installing_moves_users_who_have_no_home_action(self):
        user = self.env['res.users'].create({'name': 'Existing', 'login': 'om_existing'})
        user.action_id = False

        post_init_hook(self.env)

        self.assertEqual(user.action_id.id, self.action.id)

    def test_installing_leaves_a_chosen_home_action_alone(self):
        own = self.env.ref('base.action_res_users')
        user = self.env['res.users'].create({
            'name': 'Settled', 'login': 'om_settled', 'action_id': own.id,
        })

        post_init_hook(self.env)

        self.assertEqual(user.action_id.id, own.id)

    def test_uninstalling_hands_the_home_screen_back(self):
        """Otherwise every user is left pointing at an action that no longer exists."""
        ours = self.env['res.users'].create({'name': 'Ours', 'login': 'om_ours'})
        own_action = self.env.ref('base.action_res_users')
        theirs = self.env['res.users'].create({
            'name': 'Theirs', 'login': 'om_theirs', 'action_id': own_action.id,
        })

        uninstall_hook(self.env)

        self.assertFalse(ours.action_id)
        self.assertEqual(theirs.action_id.id, own_action.id,
                         "uninstalling must not clear an action we never set")
