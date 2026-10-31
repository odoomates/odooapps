from datetime import date, timedelta

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPrintDocument(TransactionCase):

    def test_print_filed_as_document(self):
        partner = self.env['res.partner'].create({'name': 'Holder'})
        partner_model = self.env['ir.model']._get_id('res.partner')
        doc_type = self.env['document.type'].create({'name': 'No Objection', 'model_id': partner_model})
        template = self.env['print.template'].create({
            'name': 'NOC', 'model_id': partner_model, 'body_html': '<p>No objection.</p>',
            'document_type_id': doc_type.id, 'validity_days': 30})
        issue = self.env['print.issue']._create_from_template(template, partner.ids, {'date': date(2026, 6, 1)})
        issue.action_issue()

        document = issue.document_id
        self.assertEqual((document.res_model, document.res_id, document.type_id), ('res.partner', partner.id, doc_type))
        self.assertEqual((document.number, document.date_issue), (issue.name, date(2026, 6, 1)))
        self.assertEqual(document.date_expiry, date(2026, 6, 1) + timedelta(days=30))
        self.assertEqual(document.attachment_ids.res_model, 'document.document')
        self.assertEqual(document.attachment_ids.checksum, issue.attachment_id.checksum)

        issue.action_cancel()
        self.assertFalse(document.active, 'a cancelled print no longer counts as a document')

    def test_without_document_type(self):
        partner = self.env['res.partner'].create({'name': 'Holder'})
        template = self.env['print.template'].create({
            'name': 'Letter', 'model_id': self.env['ir.model']._get_id('res.partner'), 'body_html': '<p>Hi</p>'})
        issue = self.env['print.issue']._create_from_template(template, partner.ids)
        issue.action_issue()
        self.assertFalse(issue.document_id)
