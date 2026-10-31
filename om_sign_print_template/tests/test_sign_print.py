import hashlib
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged
from odoo.tools.binary import BinaryBytes

from odoo.addons.om_sign.tests.common import blank_pdf

from .common import SignPrintCommon


@tagged('post_install', '-at_install')
class TestSignPrint(SignPrintCommon, TransactionCase):

    def notified(self, sign_request, partner):
        return self.env['mail.message'].search([
            ('model', '=', 'sign.request'), ('res_id', '=', sign_request.id), ('partner_ids', 'in', partner.ids)])

    def test_signers_from_the_roles_sign_in_order(self):
        sign_request = self.request_for_issue(send=False)
        self.assertEqual(sign_request.signer_ids.partner_id, self.customer | self.witness)
        self.assertEqual(sign_request.signer_ids.mapped('role_name'), ['Customer', 'Witness'])
        self.assertEqual(sign_request.name, 'Agreement with Acme Buyer')
        self.assertEqual(sign_request.date_deadline, fields.Date.today() + timedelta(days=14))
        self.assertEqual(sign_request.reminder_days, 3)
        self.assertEqual(sign_request.res_name, 'Acme Buyer')
        self.assertEqual(sign_request.action_open_record()['res_model'], 'print.issue', 'the record is the print')

        sign_request.action_send()
        customer, witness = self.signer_of(sign_request, self.customer), self.signer_of(sign_request, self.witness)
        self.assertEqual((customer.state, witness.state), ('to_sign', 'waiting'))
        self.assertTrue(self.notified(sign_request, self.customer), 'the customer is asked by email')
        self.assertFalse(self.notified(sign_request, self.witness), 'the witness waits for the customer')
        issue_pdf = sign_request.issue_id.attachment_id.raw.content
        self.assertEqual(sign_request.document_hash, hashlib.sha256(issue_pdf).hexdigest())
        self.assertEqual(sign_request.document_file.content, issue_pdf, 'the print is kept as it was sent')
        self.assertEqual(sign_request.document_filename, sign_request.issue_id.attachment_id.name)

        self.sign(sign_request, self.customer)
        self.sign(sign_request, self.witness)
        self.assertEqual(sign_request.state, 'signed')
        signed = sign_request.signed_attachment_id.raw.content
        self.assertEqual(sign_request.signed_hash, hashlib.sha256(signed).hexdigest())
        # the tests render the reports as HTML: the text of the print, the signatures and the certificate are in it
        self.assertIn(b'We agree with Acme Buyer', signed)
        self.assertIn(b'Wanda Witness', signed)
        self.assertIn(b'Signature Certificate', signed)
        self.assertIn(sign_request.issue_id.name.encode(), signed, 'the certificate names the print')
        self.assertIn(sign_request.document_hash.encode(), signed)
        self.assertEqual(sign_request.issue_id.sign_request_count, 1)

    def test_same_sequence_signs_together(self):
        self.template.sign_role_ids[1].sequence = 10
        sign_request = self.request_for_issue()
        self.assertEqual(sign_request.signer_ids.mapped('state'), ['to_sign', 'to_sign'])
        self.sign(sign_request, self.witness)
        self.assertEqual(sign_request.state, 'sent')
        self.sign(sign_request, self.customer)
        self.assertEqual(sign_request.state, 'signed')

    def test_email_code_of_the_template(self):
        self.template.sign_email_code = True
        sign_request = self.request_for_issue()
        self.assertTrue(sign_request.email_code)
        with self.assertRaisesRegex(UserError, 'code'):
            self.sign(sign_request, self.customer)

    def test_placeholders(self):
        self.template.body_html = '<p>Agreed.</p><p>[signature: Customer]</p><p>Thank you.</p>'
        issue = self.issue()
        body, others = issue._sign_body()
        self.assertNotIn('[signature', body)
        self.assertIn('Customer', body, 'a blank block waits for the customer')
        self.assertEqual(others, [])

        sign_request = self.env['sign.request'].with_user(self.sender)._create_for_issue(issue)
        sign_request.action_send()
        self.sign(sign_request, self.customer)
        self.sign(sign_request, self.witness)
        body, others = issue._sign_body(sign_request)
        self.assertLess(body.index('Acme Buyer'), body.index('Thank you'), 'the customer signs in the text')
        self.assertEqual([entry['name'] for entry in others], ['Wanda Witness'], 'the witness signs below')

    def test_issue_checks(self):
        draft = self.env['print.issue'].with_user(self.sender)._create_from_template(self.template,
                                                                                      self.customer.ids)
        with self.assertRaises(UserError):
            self.env['sign.request'].with_user(self.sender)._create_for_issue(draft)
        draft.action_issue()
        self.template.sign_role_ids.unlink()
        with self.assertRaises(UserError):
            draft.action_request_signature()

    def test_print_wizard_issue_and_send(self):
        context = {'active_model': 'res.partner', 'active_ids': self.customer.ids,
                   'default_template_id': self.template.id}
        wizard = Form(self.env['print.wizard'].with_user(self.sender).with_context(**context)).save()
        self.assertTrue(wizard.has_sign_roles)
        action = wizard.action_issue_sign()
        sign_request = self.env['sign.request'].browse(action['res_id'])
        self.assertEqual(sign_request.state, 'draft')
        self.assertEqual(sign_request.issue_id.state, 'issued')
        self.assertEqual(sign_request.issue_id.sign_request_count, 1)

    def test_uploaded_pdf_unchanged(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)])
        pdf = sign_request.document_file.content
        self.sign(sign_request, self.customer)
        self.assertTrue(sign_request.signed_attachment_id.raw.content.startswith(pdf),
                        'the document comes first, then the signature page')


@tagged('post_install', '-at_install')
class TestSignPrintMultiCompany(TransactionCase):

    def test_no_print_of_another_company(self):
        company_a = self.env.company
        company_b = self.env['res.company'].create({'name': 'Sign Company B'})
        sender = new_test_user(self.env, 'om_mc_sign_print_sender', groups='base.group_user,om_sign.group_sign_user',
                               company_id=company_a.id, company_ids=[Command.set((company_a | company_b).ids)])
        template_b = self.env['print.template'].create({
            'name': 'Letter of B', 'model_id': self.env['ir.model']._get_id('res.partner'),
            'company_id': company_b.id, 'body_html': '<p>Hello</p>'})
        partner = self.env['res.partner'].create({'name': 'Printed', 'email': 'printed@example.com'})
        issue = self.env['print.issue']._create_from_template(template_b, partner.ids, {'company_id': company_b.id})
        with self.assertRaises(UserError):
            self.env['sign.request'].create({
                'name': 'Contract', 'company_id': company_a.id, 'requested_by_id': sender.id,
                'document_file': BinaryBytes(blank_pdf()), 'document_filename': 'contract.pdf',
                'signer_ids': [Command.create({'partner_id': partner.id})], 'issue_id': issue.id})
