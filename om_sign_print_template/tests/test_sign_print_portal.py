from odoo.tests import HttpCase, tagged

from .common import SignPrintCommon


@tagged('post_install', '-at_install')
class TestSignPrintPortal(SignPrintCommon, HttpCase):

    def test_verify_pages(self):
        sign_request = self.request_for_issue()
        self.sign(sign_request, self.customer)
        self.sign(sign_request, self.witness)
        page = self.url_open('/sign/verify/%s' % sign_request.access_token).text
        self.assertIn(sign_request.document_hash, page)
        # the QR page of the print names its signers
        self.template.show_qr = True
        page = self.url_open('/print/verify/%s' % sign_request.issue_id.access_token).text
        self.assertIn('Signed by', page)
        self.assertIn('Wanda Witness', page)
