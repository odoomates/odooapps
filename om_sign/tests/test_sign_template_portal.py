from odoo import Command, fields
from odoo.tests import HttpCase, tagged
from odoo.tools.binary import BinaryBytes

from .common import SIGNATURE, make_pdf
from .test_sign_template import SignTemplateCommon


@tagged('post_install', '-at_install')
class TestSignTemplatePortal(SignTemplateCommon, HttpCase):
    """ The routes of the signing page for the requests of a template, and the editor. """

    def url(self, signer, suffix=''):
        return '/sign/%s/%s%s' % (signer.id, signer.sudo().access_token, suffix)

    def test_fields_routes(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids
        data = self.make_jsonrpc_request(self.url(customer, '/fields'), {})
        self.assertTrue(data['can_sign'])
        self.assertFalse(data['needs_code'])
        self.assertEqual(data['page_count'], 2)
        self.assertEqual({field['id'] for field in data['fields']}, set(customer.sudo().value_ids.ids),
                         'the fields of the signer only')
        name = next(field for field in data['fields'] if field['type'] == 'name')
        self.assertEqual((name['page'], name['pos_x'], name['pos_y']), (1, 0.1, 0.8))
        self.assertEqual(name['default'], 'Acme Buyer')
        self.assertFalse(self.make_jsonrpc_request(self.url(company, '/fields'), {})['can_sign'], 'not its turn')
        response = self.url_open('/sign/%s/%s/fields' % (company.id, customer.sudo().access_token),
                                 json={'jsonrpc': '2.0', 'method': 'call', 'params': {}})
        self.assertEqual(response.json()['error']['code'], 404, 'the link of one signer does not open another one')

        signature = self.value_of(customer, self.f_signature).id
        result = self.make_jsonrpc_request(self.url(customer, '/fields/submit'), {'values': {str(signature): 'x'}})
        self.assertIn('error', result)
        self.assertEqual(customer.state, 'to_sign')
        foreign = self.value_of(company, self.f_company_signature).id
        result = self.make_jsonrpc_request(self.url(customer, '/fields/submit'),
                                           {'values': {str(signature): SIGNATURE, str(foreign): SIGNATURE}})
        self.assertIn('own fields', result['error'])
        result = self.make_jsonrpc_request(self.url(customer, '/fields/submit'), {
            'values': {str(signature): 'data:image/png;base64,' + SIGNATURE,
                       str(self.value_of(customer, self.f_name).id): 'Acme Buyer'},
            'name': 'A. Buyer'})
        self.assertTrue(result.get('force_refresh'), result)
        self.assertEqual((customer.state, customer.signed_name), ('signed', 'A. Buyer'))
        signed_log = sign_request.sudo().log_ids.filtered(lambda log: log.event == 'signed')
        self.assertEqual(signed_log.ip, '127.0.0.1')

    def test_fields_submit_needs_fields(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)])
        result = self.make_jsonrpc_request(self.url(sign_request.signer_ids, '/fields/submit'), {'values': {}})
        self.assertIn('no fields', result['error'], 'a request without fields is signed with a signature')
        self.assertEqual(sign_request.signer_ids.state, 'to_sign')

    def test_signing_page(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids
        page = self.url_open(self.url(customer)).text
        self.assertIn('om_sign.signing_page', page, 'the fields are filled in on the pages of the document')
        self.assertNotIn('portal.signature_form', page)
        # not its turn: the document, read-only, with what the others filled so far
        self.assertIn('om_sign.signing_page', self.url_open(self.url(company)).text)
        data = self.make_jsonrpc_request(self.url(company, '/fields'), {})
        self.assertEqual((data['status'], data['fields'], data['shown']), ('waiting', [], []))
        result = self.make_jsonrpc_request(self.url(customer, '/accept'),
                                           {'name': 'Acme Buyer', 'signature': SIGNATURE})
        self.assertTrue(result.get('force_refresh'), result)
        self.assertEqual(self.value_of(customer, self.f_name).value_text, 'Acme Buyer')
        page = self.url_open(self.url(customer)).text
        self.assertIn('om_sign.signing_page', page, 'signed: the document with the values filled, read-only')
        self.assertNotIn('portal.signature_form', page)
        data = self.make_jsonrpc_request(self.url(customer, '/fields'), {})
        self.assertEqual(data['status'], 'signed')
        self.assertFalse(data['can_sign'])
        self.assertEqual({value['id'] for value in data['shown']},
                         set(customer.sudo().value_ids.filtered('is_filled').ids), 'their own values shown')
        self.assertEqual((data['signed_count'], data['signer_count']), (1, 2))
        self.assertEqual({value['id'] for value in self.make_jsonrpc_request(self.url(company, '/fields'),
                                                                               {})['others']},
                         {value['id'] for value in data['shown']}, 'the company fills its own fields now')

        self.f_text.required = True
        other = self.send_template().signer_ids[0]
        result = self.make_jsonrpc_request(self.url(other, '/accept'), {'name': 'Acme', 'signature': SIGNATURE})
        self.assertIn('Job title', result['error'], 'the signature alone does not fill a text')

    def test_signing_page_code_first(self):
        self.sign_template.email_code = True
        customer = self.send_template().signer_ids[0]
        page = self.url_open(self.url(customer)).text
        self.assertIn('Confirm your email', page)
        self.assertNotIn('om_sign.signing_page', page, 'the fields once the email is confirmed')
        customer.sudo().code_verified = True
        self.assertIn('om_sign.signing_page', self.url_open(self.url(customer)).text)

    def test_signing_page_without_own_fields(self):
        """ A role of the template without fields signs with the signature of the portal. """
        role = self.env['sign.template.role'].create({
            'template_id': self.sign_template.id, 'name': 'Witness', 'sequence': 0, 'signer_type': 'partner',
            'partner_id': self.witness.id})
        sign_request = self.send_template()
        witness = sign_request.signer_ids.filtered(lambda signer: signer.template_role_id == role)
        self.assertEqual(witness.state, 'to_sign')
        page = self.url_open(self.url(witness)).text
        self.assertIn('portal.signature_form', page)
        self.assertNotIn('om_sign.signing_page', page)

    def test_fields_of_others(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids
        self.assertEqual(self.make_jsonrpc_request(self.url(company, '/fields'), {})['others'], [],
                         'nothing signed yet')
        customer.sudo()._sign_fields({
            self.value_of(customer, self.f_signature).id: SIGNATURE,
            self.value_of(customer, self.f_name).id: 'Acme Buyer',
            self.value_of(customer, self.f_text).id: 'Buyer',
            self.value_of(customer, self.f_check).id: True,
            self.value_of(customer, self.f_date).id: '2026-01-31',
        })
        data = self.make_jsonrpc_request(self.url(company, '/fields'), {})
        self.assertTrue(data['can_sign'])
        others = {other['id']: other for other in data['others']}
        self.assertEqual(set(others), set(customer.sudo().value_ids.ids), 'the fields the customer filled')
        signature = others[self.value_of(customer, self.f_signature).id]
        self.assertEqual((signature['page'], signature['pos_y'], signature['role']), (1, 0.6, 'Customer'))
        self.assertTrue(signature['image'].startswith('data:image/png;base64,'))
        self.assertEqual(others[self.value_of(customer, self.f_text).id]['text'], 'Buyer')
        self.assertTrue(others[self.value_of(customer, self.f_check).id]['ticked'])
        self.assertEqual(others[self.value_of(customer, self.f_date).id]['text'], '01/31/2026', 'as stamped')
        self.assertEqual(self.make_jsonrpc_request(self.url(customer, '/fields'), {})['others'], [],
                         'the company did not sign yet')

    def test_signing_tour(self):
        self.f_text.required = True
        self.f_check.required = True
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids
        self.start_tour(self.url(customer), 'om_sign_signing')
        self.assertEqual((customer.state, company.state), ('signed', 'to_sign'))
        self.assertEqual(customer.signed_name, 'Acme Buyer')
        self.assertTrue(self.value_of(customer, self.f_signature).value_image)
        self.assertEqual(self.value_of(customer, self.f_text).value_text, 'Head of Purchasing')
        self.assertTrue(self.value_of(customer, self.f_check).value_bool)
        self.assertEqual(self.value_of(customer, self.f_company).value_text, 'Acme Corp')
        self.assertEqual(self.value_of(customer, self.f_date).value_text,
                         fields.Date.to_string(fields.Date.context_today(customer)))

    def test_editor_tour(self):
        template = self.env['sign.template'].create({
            'name': 'Tour Contract',
            'document_file': BinaryBytes(make_pdf(2)),
            'document_filename': 'tour.pdf',
            'role_ids': [Command.create({'name': 'Customer', 'sequence': 1, 'color': 1}),
                         Command.create({'name': 'Company', 'sequence': 2, 'color': 4})],
        })
        customer_role, company_role = template.role_ids
        self.env['sign.template.field'].create({
            'template_id': template.id, 'role_id': customer_role.id, 'type': 'name', 'page': 1,
            'pos_x': 0.1, 'pos_y': 0.1, 'width': 0.3, 'height': 0.03})
        self.start_tour('/odoo/action-om_sign.sign_template_action/%s' % template.id, 'om_sign_template_editor',
                        login='admin')
        signature = template.field_ids.filtered(lambda field: field.type == 'signature')
        self.assertEqual(len(template.field_ids), 2)
        self.assertEqual((signature.role_id, signature.label, signature.required),
                         (company_role, 'Company signature', True))
        self.assertTrue(0 <= signature.pos_x <= 1 - signature.width)
        self.assertTrue(0 <= signature.pos_y <= 1 - signature.height)
