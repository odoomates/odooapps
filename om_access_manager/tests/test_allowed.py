# Allowed Records. The test database lacks the business apps, so a test kind on
# partner tags stands in for them.
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.om_access_manager.models import om_access_allowed

TEST_KIND = ('Partner Tags', 'res.partner.category', {
    'res.partner.category': "[('id', 'in', {ids})]",
    'res.partner': "[('category_id', 'in', {ids})]",
    'res.partner.bank': "[('om_no_such_field', 'in', {ids})]",
})


@tagged('post_install', '-at_install')
class TestAllowed(TransactionCase):

    def setUp(self):
        super().setUp()
        patcher = patch.dict(om_access_allowed.ALLOWED_KINDS, {'om_test': TEST_KIND})
        patcher.start()
        self.addCleanup(patcher.stop)
        Tag = self.env['res.partner.category']
        self.red, self.blue = Tag.create({'name': 'Red'}), Tag.create({'name': 'Blue'})
        Partner = self.env['res.partner']
        self.red_partner = Partner.create({'name': 'Red One', 'category_id': [(6, 0, self.red.ids)]})
        self.blue_partner = Partner.create({'name': 'Blue One', 'category_id': [(6, 0, self.blue.ids)]})
        self.ann = new_test_user(self.env, 'om_allowed_ann', groups='base.group_user,base.group_partner_manager')
        self.bob = new_test_user(self.env, 'om_allowed_bob', groups='base.group_user,base.group_partner_manager')

    def _visible(self, user, model='res.partner', records=None):
        records = records or (self.red_partner | self.blue_partner)
        return self.env[model].with_user(user).search([('id', 'in', records.ids)])

    def test_kinds_follow_the_installed_models(self):
        kinds = dict(self.env['om.access.allowed']._selection_kinds())
        self.assertIn('om_test', kinds)
        for kind, (_label, model_name, _filters) in om_access_allowed.ALLOWED_KINDS.items():
            self.assertEqual(kind in kinds, model_name in self.env, kind)

    def test_allowed_records_and_what_belongs_to_them(self):
        self.env['om.access.profile'].create({
            'name': 'Red only', 'user_ids': [(6, 0, self.ann.ids)],
            'allowed_ids': [(0, 0, {'kind': 'om_test', 'res_id': self.red.id})],
        })
        self.assertEqual(self._visible(self.ann, 'res.partner.category', self.red | self.blue), self.red)
        self.assertEqual(self._visible(self.ann), self.red_partner)
        # a filter on a field the model lacks is left out, not an error
        self.env['res.partner.bank'].with_user(self.ann).search([])

    def test_each_users_own(self):
        self.env['om.access.profile'].create({
            'name': 'Own tag', 'user_ids': [(6, 0, (self.ann | self.bob).ids)],
            'allowed_ids': [(0, 0, {'kind': 'om_test', 'per_user': True})],
        })
        # nothing set on the user yet: nothing allowed
        self.assertFalse(self._visible(self.ann))
        self.ann.access_allowed_ids = [(0, 0, {'kind': 'om_test', 'res_id': self.red.id})]
        self.bob.access_allowed_ids = [(0, 0, {'kind': 'om_test', 'res_id': self.blue.id})]
        self.assertEqual(self._visible(self.ann), self.red_partner)
        self.assertEqual(self._visible(self.bob), self.blue_partner)

    def test_a_clear_refusal(self):
        self.env['om.access.profile'].create({
            'name': 'Red only', 'user_ids': [(6, 0, self.ann.ids)],
            'allowed_ids': [(0, 0, {'kind': 'om_test', 'res_id': self.red.id})],
        })
        with self.assertRaises(AccessError) as caught:
            self.blue_partner.with_user(self.ann).write({'name': 'Renamed'})
        self.assertIn('outside the ones allowed to you', str(caught.exception))
        self.assertNotIn('Blue One', str(caught.exception))

    def test_a_line_needs_a_record_and_an_owner(self):
        Allowed = self.env['om.access.allowed']
        profile = self.env['om.access.profile'].create({'name': 'P'})
        with self.assertRaises(ValidationError):
            Allowed.create({'kind': 'om_test', 'profile_id': profile.id})
        with self.assertRaises(ValidationError):
            Allowed.create({'kind': 'om_test', 'res_id': self.red.id})
        with self.assertRaises(ValidationError):
            Allowed.create({'kind': 'om_test', 'user_id': self.ann.id, 'per_user': True})
