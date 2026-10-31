from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged

from .common import SIGNATURE, SignCommon


@tagged('post_install', '-at_install')
class TestSignPortal(SignCommon, HttpCase):
    """ The signing page, reached from the emailed link without logging in. """

    def url(self, signer, suffix=''):
        return '/sign/%s/%s%s' % (signer.id, signer.sudo().access_token, suffix)

    def test_signing_page(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer), (20, 'Witness', self.witness)])
        customer, witness = self.signer_of(sign_request, self.customer), self.signer_of(sign_request, self.witness)

        page = self.url_open(self.url(customer))
        self.assertEqual(page.status_code, 200)
        self.assertIn('Uploaded Contract', page.text)
        self.assertIn('portal.signature_form', page.text)
        self.assertTrue(customer.date_opened)
        self.assertIn('Others sign before you', self.url_open(self.url(witness)).text)

        document = self.url_open(self.url(customer, '/document'))
        self.assertEqual(document.headers['Content-Type'], 'application/pdf')
        self.assertTrue(document.content.startswith(b'%PDF'))

        # the link of one signer does not open another one
        self.assertEqual(self.url_open('/sign/%s/%s' % (witness.id, customer.sudo().access_token)).status_code, 404)
        self.assertEqual(self.url_open('/sign/%s/wrong' % customer.id).status_code, 404)
        self.assertEqual(self.url_open('/sign/999999/wrong').status_code, 404)

        result = self.make_jsonrpc_request(self.url(customer, '/accept'),
                                           {'name': 'Acme Buyer', 'signature': SIGNATURE})
        self.assertTrue(result.get('force_refresh'), result)
        self.assertEqual(customer.state, 'signed')
        signed_log = sign_request.sudo().log_ids.filtered(lambda log: log.event == 'signed')
        self.assertEqual(signed_log.ip, '127.0.0.1', 'the address the signature came from')
        result = self.make_jsonrpc_request(self.url(customer, '/accept'), {'name': 'Again', 'signature': SIGNATURE})
        self.assertIn('error', result)
        result = self.make_jsonrpc_request(self.url(witness, '/accept'), {'name': 'Wanda', 'signature': 'not an image'})
        self.assertIn('error', result)
        self.assertEqual(witness.state, 'to_sign')

        self.make_jsonrpc_request(self.url(witness, '/accept'), {'name': 'Wanda', 'signature': SIGNATURE})
        self.assertEqual(sign_request.state, 'signed')
        signed = self.url_open(self.url(witness, '/document'))
        self.assertEqual(signed.content, sign_request.signed_attachment_id.raw.content)

    def test_draft_is_not_reachable(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)], send=False)
        self.assertEqual(self.url_open(self.url(sign_request.signer_ids)).status_code, 404)

    def test_email_code_and_decline(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)], send=False)
        sign_request.email_code = True
        sign_request.action_send()
        signer = sign_request.signer_ids
        self.assertIn('Confirm your email', self.url_open(self.url(signer)).text)
        result = self.make_jsonrpc_request(self.url(signer, '/accept'), {'name': 'Acme', 'signature': SIGNATURE})
        self.assertIn('error', result)

        self.authenticate(None, None)  # a session for the CSRF token of the forms
        with patch.object(type(signer), '_generate_code', return_value='123456'):
            page = self.url_open(self.url(signer, '/code'), data={'csrf_token': self.csrf_token()})
        self.assertIn('We sent a code', page.text)
        page = self.url_open(self.url(signer, '/code'), data={'csrf_token': self.csrf_token(), 'code': '111111'})
        self.assertIn('The code is wrong', page.text)
        self.url_open(self.url(signer, '/code'), data={'csrf_token': self.csrf_token(), 'code': '123456'})
        self.assertTrue(signer.code_verified)
        self.assertIn('portal.signature_form', self.url_open(self.url(signer)).text)

        self.url_open(self.url(signer, '/decline'), data={'csrf_token': self.csrf_token(), 'reason': 'Not mine'})
        self.assertEqual((signer.state, sign_request.state), ('declined', 'declined'))
        self.assertIn('Not mine', self.url_open(self.url(signer)).text)

    def test_my_signatures(self):
        portal_user = new_test_user(self.env, 'om_sign_portal', groups='base.group_portal', email='portal@example.com',
                                    password='om_sign_portal')
        mine = self.upload_request([(10, 'Buyer', portal_user.partner_id)])
        other = self.upload_request([(10, 'Buyer', self.customer)])
        self.authenticate('om_sign_portal', 'om_sign_portal')
        page = self.url_open('/my/signatures').text
        self.assertIn(self.url(mine.signer_ids), page)
        self.assertNotIn(self.url(other.signer_ids), page)
        counters = self.make_jsonrpc_request('/my/counters', {'counters': {'sign_count': 'common_category'}})
        self.assertEqual(counters['sign_count'], 1)

    def test_verify_page(self):
        sign_request = self.request_for_customer()
        self.sign(sign_request, self.customer)
        self.sign(sign_request, self.witness)
        page = self.url_open('/sign/verify/%s' % sign_request.access_token).text
        self.assertIn('Signed', page)
        self.assertIn(sign_request.document_hash, page)
        self.assertIn('Wanda Witness', page)
        self.assertIn('Not found', self.url_open('/sign/verify/nothing').text)
