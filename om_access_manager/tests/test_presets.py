# The one-click record filters of a data rule.
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPresets(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_access_preset_user', groups='base.group_user')
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Preset Profile', 'user_ids': [(6, 0, cls.user.ids)],
        })

    def _rule(self, model_name):
        return self.env['om.access.profile.model'].create({
            'profile_id': self.profile.id,
            'model_id': self.env['ir.model']._get(model_name).id,
        })

    def test_presets_follow_the_fields_of_the_model(self):
        presets = self._rule('res.partner').available_presets.split()
        self.assertIn('own', presets)
        self.assertIn('company', presets)
        self.assertNotIn('draft', presets)
        self.assertFalse(self._rule('res.lang').available_presets)

    def test_their_own_records(self):
        Partner = self.env['res.partner']
        mine = Partner.create({'name': 'Mine', 'user_id': self.user.id})
        other = Partner.create({'name': 'Not Mine'})
        rule = self._rule('res.partner')
        rule.action_preset_own()
        self.assertEqual(rule.domain, "[('user_id', '=', uid)]")
        found = Partner.with_user(self.user).search([('id', 'in', (mine + other).ids)])
        self.assertEqual(found, mine)

    def test_their_companies(self):
        rule = self._rule('res.partner')
        rule.action_preset_company()
        partner = self.env['res.partner'].create({'name': 'Shared Partner'})
        self.assertTrue(self.env['res.partner'].with_user(self.user).search([('id', '=', partner.id)]))

    def test_edit_drafts_only_and_all_records(self):
        model_name = next(
            (name for name, model in self.env.registry.items()
             if not model._abstract and not model._transient and model._auto
             and 'state' in model._fields and model._fields['state'].type == 'selection'
             and 'draft' in dict(model._fields['state']._description_selection(self.env))),
            None)
        if not model_name:
            self.skipTest("no model with a draft state is installed")
        rule = self._rule(model_name)
        rule.action_preset_draft()
        self.assertEqual(rule.domain_write, "[('state', '=', 'draft')]")
        self.assertEqual(rule.domain_unlink, "[('state', '=', 'draft')]")
        self.assertFalse(rule.domain)
        rule.action_clear_filters()
        self.assertFalse(rule.domain_write or rule.domain_unlink)

    def test_field_switches(self):
        # stand-ins for the business app fields, plus missing ones that must be skipped
        from unittest.mock import patch

        from odoo.addons.om_access_manager.models import om_access_profile
        switches = (('hide_costs', (('res.partner', 'email'), ('om.no.model', 'x'),
                                    ('res.partner', 'om_no_field'))),
                    ('hide_sale_prices', (('res.partner', 'phone'),)))
        with patch.object(om_access_profile, 'FIELD_SWITCHES', switches):
            self.profile.hide_costs = True
            rules = self.env['om.access.profile']._resolve(self.user.id)
            self.assertEqual(rules.field_mode('res.partner', 'email'), 'hide')
            self.assertIsNone(rules.field_mode('res.partner', 'phone'))
            # the switch never weakens a stricter or equal line, and adds to the others
            self.profile.hide_sale_prices = True
            rules = self.env['om.access.profile']._resolve(self.user.id)
            self.assertEqual(rules.field_mode('res.partner', 'phone'), 'hide')
