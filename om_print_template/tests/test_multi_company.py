from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPrintMultiCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Prints Company B'})
        cls.user_a = new_test_user(cls.env, 'om_print_mc_a', groups='base.group_user,base.group_partner_manager',
                                   company_id=cls.company_a.id, company_ids=[Command.set(cls.company_a.ids)])
        model_id = cls.env['ir.model']._get_id('res.partner')
        Template = cls.env['print.template']
        cls.shared = Template.create({'name': 'Shared Letter', 'model_id': model_id, 'body_html': '<p>Hi</p>'})
        cls.template_b = Template.create({'name': 'Letter B', 'model_id': model_id, 'body_html': '<p>Hi</p>',
                                          'company_id': cls.company_b.id})
        cls.partner_a = cls.env['res.partner'].create({'name': 'Partner A', 'company_id': cls.company_a.id})

    def test_templates(self):
        Template = self.env['print.template'].with_user(self.user_a)
        self.assertIn(self.shared, Template.search([]))
        self.assertNotIn(self.template_b, Template.search([]))
        with self.assertRaises(AccessError):
            self.template_b.with_user(self.user_a).read(['name'])

    def test_issue(self):
        issue = self.env['print.issue']._create_from_template(self.shared, self.partner_a.ids)
        self.assertEqual(issue.company_id, self.company_a, 'a shared template prints for the company of the record')
        with self.assertRaises(UserError):
            self.env['print.issue']._create_from_template(self.template_b, self.partner_a.ids)
