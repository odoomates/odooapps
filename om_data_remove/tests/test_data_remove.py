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
