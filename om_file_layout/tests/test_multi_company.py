from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestFileLayoutMultiCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Layouts Company B'})
        cls.user_a = new_test_user(cls.env, 'om_file_mc_a', groups='base.group_user,base.group_partner_manager',
                                   company_id=cls.company_a.id, company_ids=[Command.set(cls.company_a.ids)])
        model_id = cls.env['ir.model']._get_id('res.partner')
        column = [(0, 0, {'name': 'Name', 'expression': 'record.name'})]
        Layout = cls.env['file.layout']
        cls.shared = Layout.create({'name': 'Shared Partners', 'model_id': model_id, 'column_ids': column})
        cls.layout_b = Layout.create({'name': 'Partners B', 'model_id': model_id, 'column_ids': column,
                                      'company_id': cls.company_b.id})
        cls.partner = cls.env['res.partner'].create({'name': 'Gamma Partner'})

    def export(self, layout, user):
        context = {'active_model': 'res.partner', 'active_ids': self.partner.ids, 'default_layout_id': layout.id}
        return Form(self.env['file.export.wizard'].with_user(user).with_context(**context)).save()._export()

    def test_layouts(self):
        Layout = self.env['file.layout'].with_user(self.user_a)
        self.assertIn(self.shared, Layout.search([]))
        self.assertNotIn(self.layout_b, Layout.search([]))
        with self.assertRaises(AccessError):
            self.layout_b.with_user(self.user_a).read(['name'])

    def test_export(self):
        export = self.export(self.shared, self.user_a)
        self.assertEqual(export.company_id, self.company_a, 'a shared layout exports for the current company')
        both = new_test_user(self.env, 'om_file_mc_both', groups='base.group_user,base.group_partner_manager',
                             company_id=self.company_a.id,
                             company_ids=[Command.set((self.company_a | self.company_b).ids)])
        with self.assertRaises(UserError):
            self.export(self.layout_b, both)
