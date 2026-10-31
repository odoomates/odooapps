from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import SIGNATURE
from .test_sign_template import SignTemplateCommon


@tagged('post_install', '-at_install')
class TestSignShare(SignTemplateCommon, HttpCase):
    """ The shared link of a template, and the read-only pages: the copy recipients' and the signers'. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.f_company.required = False  # a visitor works for no company
        cls.observer = cls.env['res.partner'].create({'name': 'Olga Observer', 'email': 'olga@example.com'})
        cls.Visit = cls.env['sign.share.visit']

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)  # a session for the CSRF token of the forms

    def share(self, template=None):
        template = template or self.sign_template
        template.with_user(self.sender).share_enabled = True
        return template

    def link(self, template=None, suffix=''):
        template = template or self.sign_template
        return '/sign/share/%s/%s%s' % (template.id, template.sudo().share_token, suffix)

    def ask_code(self, name='Vera Visitor', email='vera@example.com', template=None, **data):
        with patch.object(type(self.Visit), '_generate_code', return_value='123456'):
            return self.url_open(self.link(template, '/code'), data={
                'csrf_token': self.csrf_token(), 'name': name, 'email': email, **data})

    def last_visit(self):
        return self.Visit.sudo().search([], limit=1)

    # ------------------------------------------------------------------
    # Sharing
    # ------------------------------------------------------------------

    def test_share_toggle(self):
        template = self.share()
        token = template.sudo().share_token
        self.assertTrue(token)
        self.assertEqual(template.share_user_id, self.sender)
        self.assertEqual(template.share_role_id, self.customer_role)
        self.assertTrue(template.share_url.endswith('/sign/share/%s/%s' % (template.id, token)))
        self.assertEqual(self.url_open(self.link()).status_code, 200)
        self.assertIn('o_sign_share_start', self.url_open(self.link()).text)

        template.with_user(self.sender).action_regenerate_share_token()
        self.assertNotEqual(template.sudo().share_token, token)
        self.assertEqual(self.url_open('/sign/share/%s/%s' % (template.id, token)).status_code, 404,
                         'the link given before no longer opens')
        self.assertEqual(self.url_open('/sign/share/%s/wrong' % template.id).status_code, 404)
        other = self.sign_template.copy()
        other.share_enabled = True
        self.assertEqual(self.url_open('/sign/share/%s/%s' % (other.id, template.sudo().share_token)).status_code,
                         404, 'the token of another template')

        link = self.link()
        template.with_user(self.sender).share_enabled = False
        self.assertFalse(template.sudo().share_token)
        self.assertFalse(template.share_url)
        self.assertEqual(self.url_open(link).status_code, 404, 'sharing stopped')
        self.assertEqual(self.url_open(link + '/code', data={
            'csrf_token': self.csrf_token(), 'name': 'Vera', 'email': 'vera@example.com'}).status_code, 404)
        self.assertFalse(self.Visit.sudo().search([]))

    def test_share_needs_one_visitor_role(self):
        self.company_role.write({'signer_type': 'choose', 'partner_id': False})
        self.assertTrue(self.sign_template.share_problem)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.share()
        self.company_role.signer_type = 'requester'
        template = self.share()
        self.assertFalse(template.share_problem)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env['sign.template'].with_user(self.sender).editor_save(template.id, {
                'roles': [{'id': role.id, 'name': role.name, 'sequence': role.sequence, 'signer_type': 'choose'}
                          for role in template.role_ids], 'fields': []})
        # the roles changed by other means: the link no longer opens
        self.company_role.signer_type = 'choose'
        self.assertEqual(self.url_open(self.link()).status_code, 404)

    def test_share_link_signs(self):
        self.sign_template.write({'cc_partner_ids': self.observer.ids, 'email_code': True})
        self.share()
        page = self.ask_code(name='Vera Visitor', email='Vera@Example.com')
        self.assertIn('We sent a code to', page.text)
        self.assertFalse(self.env['sign.request'].search([('sign_template_id', '=', self.sign_template.id)]),
                         'nothing made before the email is confirmed')
        visit = self.last_visit()
        self.assertEqual((visit.name, visit.email, visit.ip), ('Vera Visitor', 'vera@example.com', '127.0.0.1'))
        mail = self.env['mail.mail'].sudo().search([('email_to', '=', 'vera@example.com')])
        self.assertIn('123456', str(mail.body_html))

        verify = self.link(suffix='/verify')
        page = self.url_open(verify, data={'csrf_token': self.csrf_token(), 'visit': 'nothing', 'code': '123456'})
        self.assertIn('start again', page.text)
        page = self.url_open(verify, data={'csrf_token': self.csrf_token(),
                                           'visit': visit.sudo().access_token, 'code': '000000'})
        self.assertIn('The code is wrong', page.text)
        self.assertFalse(visit.request_id)
        page = self.url_open(verify, data={'csrf_token': self.csrf_token(),
                                           'visit': visit.sudo().access_token, 'code': '123456'})
        sign_request = visit.request_id
        self.assertTrue(sign_request)
        visitor, company = sign_request.signer_ids
        self.assertEqual(page.url, self.base_url() + '/sign/%s/%s' % (visitor.id, visitor.sudo().access_token),
                         'straight to the signing page')
        self.assertIn('om_sign.signing_page', page.text, 'no code asked again')
        self.assertEqual(sign_request.source, 'share_link')
        self.assertEqual(sign_request.state, 'sent')
        self.assertEqual(sign_request.requested_by_id, self.sender, 'as the user who shared it')
        self.assertEqual(sign_request.company_id, self.env.company)
        self.assertEqual(sign_request.cc_partner_ids, self.observer)
        self.assertEqual((visitor.partner_id.name, visitor.partner_id.email), ('Vera Visitor', 'vera@example.com'))
        self.assertEqual((visitor.template_role_id, visitor.state, visitor.code_verified),
                         (self.customer_role, 'to_sign', True))
        self.assertEqual((company.partner_id, company.state), (self.company_contact, 'waiting'))
        self.assertEqual(self.sign_template.share_request_count, 1)
        page = self.url_open(verify, data={'csrf_token': self.csrf_token(),
                                           'visit': visit.sudo().access_token, 'code': '123456'})
        self.assertIn('start again', page.text, 'one request per code')
        self.assertEqual(len(self.sign_template.request_ids), 1)

        # the others sign next, as usual
        self.sign(sign_request, visitor.partner_id)
        self.assertEqual(company.state, 'to_sign')
        self.assertTrue(company._needs_code(), 'the code of the template, for the others')

    def test_share_link_existing_contact(self):
        self.share()
        self.ask_code(name='Someone Else', email='buyer@example.com')
        visit = self.last_visit()
        self.url_open(self.link(suffix='/verify'), data={
            'csrf_token': self.csrf_token(), 'visit': visit.sudo().access_token, 'code': '123456'})
        self.assertEqual(visit.request_id.signer_ids[0].partner_id, self.customer, 'the contact of the email')

    def test_share_code_attempts(self):
        self.share()
        self.ask_code()
        visit = self.last_visit()
        for _attempt in range(5):
            self.url_open(self.link(suffix='/verify'), data={
                'csrf_token': self.csrf_token(), 'visit': visit.sudo().access_token, 'code': '000000'})
        page = self.url_open(self.link(suffix='/verify'), data={
            'csrf_token': self.csrf_token(), 'visit': visit.sudo().access_token, 'code': '123456'})
        self.assertIn('The code is wrong', page.text, 'too many wrong codes: a new one is needed')
        self.assertFalse(visit.request_id)
        page = self.url_open(self.link(suffix='/code'), data={
            'csrf_token': self.csrf_token(), 'visit': visit.sudo().access_token})
        self.assertIn('A code was sent a moment ago', page.text, 'one code a minute')

    def test_share_rate_limit(self):
        self.share()
        self.env['ir.config_parameter'].sudo().set_int('om_sign.share_limit_email', 2)
        self.env['ir.config_parameter'].sudo().set_int('om_sign.share_limit_ip', 3)
        self.assertIn('We sent a code', self.ask_code(email='vera@example.com').text)
        self.assertIn('We sent a code', self.ask_code(email='VERA@example.com').text)
        page = self.ask_code(email='vera@example.com')
        self.assertIn('Too many requests', page.text, 'by email')
        self.assertIn('We sent a code', self.ask_code(email='other@example.com').text)
        self.assertIn('Too many requests', self.ask_code(email='third@example.com').text, 'by IP address')
        self.assertEqual(self.Visit.sudo().search_count([]), 3)

    def test_share_checks(self):
        self.share()
        self.assertIn('valid email', self.ask_code(email='not an email').text)
        self.assertIn('Write your name', self.ask_code(name=' ').text)
        with mute_logger('odoo.addons.om_sign.controllers.main'):
            page = self.ask_code(website='http://spam.example.com')
        self.assertEqual(page.status_code, 200, 'a robot sees nothing different')
        self.assertFalse(self.Visit.sudo().search([]), 'nothing made for a robot')
        self.assertFalse(self.env['mail.mail'].sudo().search([('email_to', '=', 'vera@example.com')]))
        with mute_logger('odoo.http'):
            response = self.url_open(self.link(suffix='/code'), data={'name': 'Vera', 'email': 'vera@example.com'})
        self.assertEqual(response.status_code, 400, 'the CSRF token is required')

    def test_share_company(self):
        company = self.env['res.company'].create({'name': 'Second Company', 'email': 'second@example.com'})
        self.sender.write({'company_ids': [(4, company.id)]})
        template = self.sign_template.copy({'company_id': company.id})
        template.with_user(self.sender).with_context(
            allowed_company_ids=[company.id, self.env.company.id]).share_enabled = True
        self.ask_code(template=template)
        visit = self.last_visit()
        self.assertEqual(visit.company_id, company)
        mail = self.env['mail.mail'].sudo().search([('email_to', '=', 'vera@example.com')])
        self.assertIn('second@example.com', mail.email_from, 'from the company of the template')
        self.url_open(self.link(template, '/verify'), data={
            'csrf_token': self.csrf_token(), 'visit': visit.sudo().access_token, 'code': '123456'})
        self.assertEqual(visit.request_id.company_id, company)
        self.assertEqual(visit.request_id.signer_ids.company_id, company)

    def test_share_tour(self):
        self.sign_template.cc_partner_ids = self.observer
        self.share()
        with patch.object(type(self.Visit), '_generate_code', return_value='123456'):
            self.start_tour(self.link(), 'om_sign_share')
        sign_request = self.last_visit().request_id
        visitor, company = sign_request.signer_ids
        self.assertEqual(visitor.partner_id.email, 'vera@example.com')
        self.assertEqual((visitor.state, company.state), ('signed', 'to_sign'))
        self.assertTrue(self.value_of(visitor, self.f_signature).value_image)

    # ------------------------------------------------------------------
    # The copy recipients' page
    # ------------------------------------------------------------------

    def copy_url(self, sign_request, partner, suffix=''):
        return sign_request._get_copy_url(partner).removeprefix(sign_request.get_base_url()) + suffix

    def test_copy_page(self):
        self.sign_template.cc_partner_ids = self.observer
        sign_request = self.send_template()
        url = self.copy_url(sign_request, self.observer)
        page = self.url_open(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn('om_sign.signing_page', page.text)
        data = self.make_jsonrpc_request(url + '/fields', {})
        self.assertEqual((data['status'], data['fields'], data['shown'], data['can_sign']),
                         ('copy_waiting', [], [], False))
        customer, company = sign_request.signer_ids
        self.sign(sign_request, self.customer)
        data = self.make_jsonrpc_request(url + '/fields', {})
        self.assertEqual({value['id'] for value in data['shown']},
                         set(customer.sudo().value_ids.filtered('is_filled').ids), 'the fields filled so far')
        document = self.url_open(url + '/document')
        self.assertEqual(document.headers['Content-Type'], 'application/pdf')
        self.assertEqual(document.content, sign_request.document_file.content)

        # nothing else is reached from the link
        self.assertEqual(self.url_open(url[:-4] + 'abcd').status_code, 404)
        self.assertEqual(self.url_open(self.copy_url(sign_request, self.customer)).status_code, 404,
                         'not a copy recipient')
        other = self.send_template()
        self.assertEqual(self.url_open(url.replace('/%s/' % sign_request.id, '/%s/' % other.id)).status_code, 404)

        self.sign(sign_request, self.company_contact)
        data = self.make_jsonrpc_request(url + '/fields', {})
        self.assertEqual((data['status'], data['shown']), ('copy_completed', []), 'the signed PDF holds them')
        document = self.url_open(url + '/document?download=1')
        self.assertEqual(document.content, sign_request.signed_attachment_id.raw.content)
        self.assertIn('attachment', document.headers['Content-Disposition'])

    def test_signed_pdf_sent_when_signed_from_the_link(self):
        """ The last signer signs as the public user: everyone still gets the signed PDF attached. """
        self.sign_template.cc_partner_ids = self.observer
        sign_request = self.send_template()
        self.sign(sign_request, self.customer)
        company = sign_request.signer_ids[1]
        signature = self.value_of(company, self.f_company_signature).id
        result = self.make_jsonrpc_request('/sign/%s/%s/fields/submit' % (company.id, company.sudo().access_token),
                                           {'values': {str(signature): SIGNATURE}})
        self.assertTrue(result.get('force_refresh'), result)
        self.assertEqual(sign_request.state, 'signed')
        signed = self.env['mail.message'].sudo().search([
            ('model', '=', 'sign.request'), ('res_id', '=', sign_request.id),
            ('subject', '=', 'Signed: Service Contract')])
        self.assertEqual(len(signed), 2, 'to the signers, and to the copy recipient')
        for message in signed:
            self.assertEqual(message.attachment_ids, sign_request.signed_attachment_id)
            self.assertEqual(message.author_id, self.sender.partner_id, 'from the person who sent it')
        self.assertIn(self.observer, signed.partner_ids)

    def test_copy_page_of_a_draft(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)], send=False)
        sign_request.cc_partner_ids = self.observer
        self.assertEqual(self.url_open(self.copy_url(sign_request, self.observer)).status_code, 404)

    def test_signed_page_readonly(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids
        self.sign(sign_request, self.customer)
        self.sign(sign_request, self.company_contact)
        url = '/sign/%s/%s' % (customer.id, customer.sudo().access_token)
        self.assertIn('om_sign.signing_page', self.url_open(url).text)
        data = self.make_jsonrpc_request(url + '/fields', {})
        self.assertEqual((data['status'], data['shown']), ('completed', []))
        self.assertEqual(self.url_open(url + '/document').content, sign_request.signed_attachment_id.raw.content)

    def test_readonly_tour(self):
        self.sign_template.cc_partner_ids = self.observer
        sign_request = self.send_template()
        self.sign(sign_request, self.customer)
        self.start_tour(self.copy_url(sign_request, self.observer), 'om_sign_readonly')
