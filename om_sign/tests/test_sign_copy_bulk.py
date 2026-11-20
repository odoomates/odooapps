from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged

from .test_sign_template import SignTemplateCommon


@tagged('post_install', '-at_install')
class TestSignCopyBulk(SignTemplateCommon, TransactionCase):
    """ The copy recipients of a request, and the templates sent in bulk. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.observer = cls.env['res.partner'].create({'name': 'Olga Observer', 'email': 'olga@example.com'})
        cls.f_company.required = False  # the contacts sent to in bulk work for no company

    def messages_to(self, sign_request, partner):
        return self.env['mail.message'].sudo().search([
            ('model', '=', 'sign.request'), ('res_id', '=', sign_request.id), ('partner_ids', 'in', partner.ids)])

    def sign_all(self, sign_request):
        for signer in sign_request.signer_ids:
            self.sign(sign_request, signer.partner_id)

    # ------------------------------------------------------------------
    # Copy recipients
    # ------------------------------------------------------------------

    def test_copy_recipients(self):
        self.sign_template.cc_partner_ids = self.observer
        sign_request = self.send_template()
        self.assertEqual(sign_request.cc_partner_ids, self.observer, 'the default of the template')
        self.assertNotIn(self.observer, sign_request.signer_ids.partner_id, 'they do not sign')
        sent = self.messages_to(sign_request, self.observer)
        self.assertEqual(sent.mapped('subject'), ['Sent for signature: Service Contract'])
        self.assertIn('Acme Buyer', sent.body, 'who it was sent to')
        self.assertIn(sign_request._get_copy_url(self.observer), sent.body)
        mail = self.env['mail.mail'].sudo().search([('mail_message_id', '=', sent.id)])
        self.assertEqual(mail.recipient_ids, self.observer)

        self.sign_all(sign_request)
        self.assertEqual(sign_request.state, 'signed')
        signed = self.messages_to(sign_request, self.observer) - sent
        self.assertEqual(signed.subject, 'Signed: Service Contract')
        self.assertEqual(signed.attachment_ids, sign_request.signed_attachment_id, 'the signed PDF')
        self.assertIn(sign_request._get_copy_url(self.observer), signed.body, 'their link to the signed document')
        to_signers = self.messages_to(sign_request, self.customer).filtered(
            lambda message: message.subject == 'Signed: Service Contract')
        self.assertNotIn(self.observer, to_signers.partner_ids, 'their own email, with their own link')
        self.assertNotIn('/sign/copy/', to_signers.body)

    def test_copy_recipients_told_once_signed_only(self):
        self.sign_template.write({'cc_partner_ids': self.observer.ids, 'cc_notify_sent': False})
        sign_request = self.send_template()
        self.assertFalse(sign_request.cc_notify_sent)
        self.assertFalse(self.messages_to(sign_request, self.observer), 'not told when sent')
        self.sign_all(sign_request)
        self.assertEqual(self.messages_to(sign_request, self.observer).attachment_ids,
                         sign_request.signed_attachment_id)

    def test_copy_recipients_of_a_draft(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)], send=False)
        sign_request.cc_partner_ids = self.observer
        sign_request.action_send()
        self.assertEqual(len(self.messages_to(sign_request, self.observer)), 1)
        with self.assertRaises(UserError):
            sign_request.with_user(self.sender).cc_partner_ids = False

    def test_copy_token(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)], send=False)
        sign_request.cc_partner_ids = self.observer
        token = sign_request._get_copy_token(self.observer)
        self.assertTrue(sign_request._check_copy_token(self.observer, token))
        self.assertFalse(sign_request._check_copy_token(self.customer, token), 'theirs only')
        self.assertFalse(sign_request._check_copy_token(self.customer, sign_request._get_copy_token(self.customer)),
                         'a copy recipient only')
        other = self.upload_request([(10, 'Buyer', self.customer)], send=False)
        other.cc_partner_ids = self.observer
        self.assertFalse(other._check_copy_token(self.observer, token), 'for this request only')
        sign_request.cc_partner_ids = False
        self.assertFalse(sign_request._check_copy_token(self.observer, token), 'no longer a copy recipient')

    def test_send_wizard_copies(self):
        wizard = Form(self.env['sign.send'].with_user(self.sender).with_context(
            default_template_id=self.sign_template.id))
        wizard.cc_partner_ids.add(self.observer)
        with wizard.line_ids.edit(0) as line:
            line.partner_id = self.customer
        sign_request = self.env['sign.request'].browse(wizard.save().action_send()['res_id'])
        self.assertEqual(sign_request.cc_partner_ids, self.observer)
        self.assertEqual(sign_request.source, 'send')

    # ------------------------------------------------------------------
    # Bulk send
    # ------------------------------------------------------------------

    def bulk_wizard(self, partners, template=None):
        wizard = Form(self.env['sign.send'].with_user(self.sender).with_context(
            default_template_id=(template or self.sign_template).id, default_bulk=True),
            view='om_sign.sign_send_view_form_bulk')
        for partner in partners:
            wizard.bulk_partner_ids.add(partner)
        return wizard

    def make_partners(self, count, prefix='Client'):
        return self.env['res.partner'].create([
            {'name': '%s %s' % (prefix, number), 'email': '%s%s@example.com' % (prefix.lower(), number)}
            for number in range(1, count + 1)])

    def test_bulk_send(self):
        partners = self.make_partners(3)
        wizard = self.bulk_wizard(partners)
        self.assertEqual(wizard.bulk_role_id, self.customer_role, 'the role chosen when sending')
        wizard.cc_partner_ids.add(self.observer)
        wizard.message = 'Our new terms'
        action = wizard.save().action_send()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertIn('3 requests are sent', action['params']['message'])
        requests = self.env['sign.request'].search(action['params']['next']['domain'])
        self.assertEqual(len(requests), 3)
        self.assertEqual(sorted(requests.mapped('name')),
                         ['Service Contract - Client 1', 'Service Contract - Client 2', 'Service Contract - Client 3'])
        self.assertEqual(set(requests.mapped('state')), {'sent'})
        self.assertEqual(set(requests.mapped('source')), {'bulk'})
        self.assertEqual(set(requests.mapped('message')), {'Our new terms'})
        self.assertEqual(requests.cc_partner_ids, self.observer)
        for partner in partners:
            sign_request = requests.filtered(lambda request, partner=partner: request.name.endswith(partner.name))
            customer, company = sign_request.signer_ids
            self.assertEqual((customer.partner_id, company.partner_id), (partner, self.company_contact))
            self.assertEqual(customer.state, 'to_sign')
            self.assertEqual(len(sign_request.sudo().value_ids), 8, 'its own fields')
            self.assertTrue(self.messages_to(sign_request, partner), 'asked to sign')
        self.assertEqual(len(set(requests.signer_ids.sudo().mapped('access_token'))), 6, 'independent links')
        self.assertEqual(len(set(requests.sudo().mapped('access_token'))), 3)
        # each request is signed on its own
        first = requests[0]
        self.sign_all(first)
        self.assertEqual(first.state, 'signed')
        self.assertEqual(set((requests - first).mapped('state')), {'sent'})

    def test_bulk_send_checks(self):
        no_email = self.env['res.partner'].create({'name': 'No Email'})
        with self.assertRaisesRegex(UserError, 'No Email'):
            self.bulk_wizard(self.make_partners(1) | no_email).save().action_send()
        twin = self.env['res.partner'].create({'name': 'Client Twin', 'email': 'CLIENT1@example.com'})
        with self.assertRaisesRegex(UserError, 'same email'):
            self.bulk_wizard(self.make_partners(1) | twin).save().action_send()
        with self.assertRaisesRegex(UserError, 'Choose the contacts'):
            self.bulk_wizard([]).save().action_send()
        # the other roles are the same in every request: chosen in the wizard
        wizard = self.bulk_wizard(self.make_partners(2, 'Other')).save()
        wizard.line_ids.filtered(lambda line: line.role_id == self.company_role).partner_id = False
        with self.assertRaisesRegex(UserError, 'Choose who signs as Company'):
            wizard.action_send_bulk()
        self.assertFalse(self.env['sign.request'].search([('source', '=', 'bulk'),
                                                          ('sign_template_id', '=', self.sign_template.id)]))

    def test_bulk_send_queued(self):
        partners = self.make_partners(25)
        cron = self.env.ref('om_sign.ir_cron_sign_send_queued')
        triggers = self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)])
        action = self.bulk_wizard(partners).save().action_send()
        self.assertIn('25 requests are queued', action['params']['message'])
        requests = self.env['sign.request'].search(action['params']['next']['domain'])
        self.assertEqual(len(requests), 25)
        self.assertEqual(set(requests.mapped('state')), {'draft'})
        self.assertTrue(all(requests.mapped('send_queued')))
        self.assertEqual(self.env['ir.cron.trigger'].search_count([('cron_id', '=', cron.id)]), triggers + 1,
                         'sent in the background')
        # one of them can no longer be sent
        failing = requests.filtered(lambda request: request.name.endswith('Client 7'))
        partners.filtered(lambda partner: partner.name == 'Client 7').email = False
        with patch.object(self.env.registry['ir.cron'], '_commit_progress', return_value=float('inf')):
            self.env['sign.request']._cron_send_queued()
        sent = requests - failing
        self.assertEqual(set(sent.mapped('state')), {'sent'})
        self.assertFalse(any(requests.mapped('send_queued')))
        self.assertEqual(sent.mapped('requested_by_id'), self.sender, 'sent as the user who sent them')
        self.assertEqual(sent.log_ids.filtered(lambda log: log.event == 'sent').user_id, self.sender)
        self.assertEqual(failing.state, 'draft')
        self.assertIn('Not sent', failing.message_ids[0].body)
