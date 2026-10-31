from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPrintDocumentMultiCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env['res.company'].create({'name': 'Print Documents Company B'})
        cls.model_id = cls.env['ir.model']._get_id('res.partner')
        DocumentType = cls.env['document.type']
        cls.shared_type = DocumentType.create({'name': 'Shared NOC', 'model_id': cls.model_id})
        cls.type_b = DocumentType.create({'name': 'NOC B', 'model_id': cls.model_id, 'company_id': cls.company_b.id})

    def test_document_type_of_another_company(self):
        with self.assertRaises(UserError):
            self.env['print.template'].create({
                'name': 'NOC A', 'model_id': self.model_id, 'body_html': '<p>No objection.</p>',
                'company_id': self.env.company.id, 'document_type_id': self.type_b.id})

    def test_document_of_the_company_of_the_print(self):
        template = self.env['print.template'].create({
            'name': 'Shared NOC', 'model_id': self.model_id, 'body_html': '<p>No objection.</p>',
            'document_type_id': self.shared_type.id})
        partner_b = self.env['res.partner'].create({'name': 'Holder B', 'company_id': self.company_b.id})
        issue = self.env['print.issue']._create_from_template(template, partner_b.ids)
        issue.action_issue()
        self.assertEqual((issue.company_id, issue.document_id.company_id), (self.company_b, self.company_b))
