from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

# This module deletes with raw SQL and commits at once, so nothing here removes anything: the tests cover who is
# allowed to run it, what it does with a model it does not know, and the sequences it resets.


@tagged('post_install', '-at_install')
class TestDataRemove(TransactionCase):

    def setUp(self):
        super().setUp()
        self.settings = self.env['res.config.settings'].create({})

    def test_only_the_settings_administrators_may_remove(self):
        user = new_test_user(self.env, login='data_remove_user', groups='base.group_user')
        as_user = self.settings.with_user(user)
        self.assertFalse(as_user._remove_sales())
        self.assertFalse(as_user._remove_data(['res.partner']))
        # nothing was deleted
        self.assertTrue(self.env['res.partner'].search_count([]))

    def test_an_unknown_model_is_skipped(self):
        # a model that is not installed must not stop the removal, and must not delete anything either
        self.assertTrue(self.settings._remove_data(['no.such.model.here']))
        self.assertTrue(self.env['res.partner'].search_count([]))

    def test_the_sequences_are_reset(self):
        sequence = self.env['ir.sequence'].create({
            'name': 'Data Remove Test', 'code': 'data.remove.test', 'prefix': 'DRT/', 'number_next': 42,
        })
        self.assertTrue(self.settings._remove_data([], ['DRT']))
        self.assertEqual(sequence.number_next, 1)

    def test_every_button_of_the_wizard_exists(self):
        for name in ('_remove_sales', '_remove_product', '_remove_data'):
            self.assertTrue(callable(getattr(self.settings, name, None)), name)

    def test_the_screen_counts_and_asks_for_confirmation(self):
        from unittest.mock import patch
        from odoo.addons.om_data_remove.models import model
        # a table present on every database stands for the messages
        patcher = patch.dict(model.REMOVAL_MODELS, {'message': ['res.partner']})
        patcher.start()
        self.addCleanup(patcher.stop)
        settings = self.env['res.config.settings'].create({})
        self.assertEqual(settings.om_remove_count_message, settings._om_removal_count('message'))
        self.assertGreater(settings.om_remove_count_message, 0)
        self.assertGreaterEqual(settings.om_remove_count_all, settings.om_remove_count_message)

        action = settings.with_context(om_removal='message').action_om_open_removal()
        wizard = self.env[action['res_model']].with_context(action['context']).create({})
        self.assertEqual(wizard.record_count, settings.om_remove_count_message)
        self.assertIn('Contact', wizard.model_names)
        # nothing is deleted without the confirmation word, and nothing is deleted here at all
        with patch.object(type(settings), 'action_remove_message') as remove:
            wizard.confirmation = 'yes'
            with self.assertRaises(UserError):
                wizard.action_remove()
            remove.assert_not_called()
            wizard.confirmation = ' delete '
            wizard.action_remove()
            remove.assert_called_once()

        user = new_test_user(self.env, login='data_remove_viewer', groups='base.group_user')
        with self.assertRaises(AccessError):
            wizard.with_user(user).action_remove()
