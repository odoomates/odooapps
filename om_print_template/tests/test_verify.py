from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestVerify(HttpCase):

    def test_verify_page(self):
        partner = self.env['res.partner'].create({'name': 'Verified Holder'})
        template = self.env['print.template'].create({
            'name': 'Confirmation', 'model_id': self.env['ir.model']._get_id('res.partner'),
            'body_html': '<p>Hello</p>', 'show_qr': True})
        issue = self.env['print.issue']._create_from_template(template, partner.ids)
        issue.action_issue()
        url = '/print/verify/%s' % issue.access_token

        page = self.url_open(url).text
        self.assertIn('Genuine', page)
        self.assertIn('Verified Holder', page)
        self.assertIn(issue.name, page)
        self.assertNotIn('Hello', page, 'the text of the print is not shown')

        issue.action_cancel()
        self.assertIn('Cancelled', self.url_open(url).text)

        template.show_qr = False
        self.assertIn('Not found', self.url_open(url).text, 'only prints offering the QR are verified')
        self.assertIn('Not found', self.url_open('/print/verify/nothing').text)
        draft = self.env['print.issue']._create_from_template(template, partner.ids)
        template.show_qr = True
        self.assertIn('Not found', self.url_open('/print/verify/%s' % draft.access_token).text)
