import hashlib
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.binary import BinaryBytes

from .common import SIGNATURE, SignCommon


@tagged('post_install', '-at_install')
class TestSign(SignCommon, TransactionCase):

    def events(self, sign_request, signer=None):
        logs = sign_request.sudo().log_ids
        if signer:
            logs = logs.filtered(lambda log: log.signer_id == signer)
        return logs.mapped('event')

    def notified(self, sign_request, partner):
        return self.env['mail.message'].search([
            ('model', '=', 'sign.request'), ('res_id', '=', sign_request.id), ('partner_ids', 'in', partner.ids)])

    def test_signers_sign_in_order(self):
        sign_request = self.request_for_customer(send=False)
        self.assertEqual(sign_request.res_name, 'Acme Buyer')

        sign_request.action_send()
        customer, witness = self.signer_of(sign_request, self.customer), self.signer_of(sign_request, self.witness)
        self.assertEqual(sign_request.state, 'sent')
        self.assertEqual((customer.state, witness.state), ('to_sign', 'waiting'))
        self.assertTrue(self.notified(sign_request, self.customer), 'the customer is asked by email')
        self.assertFalse(self.notified(sign_request, self.witness), 'the witness waits for the customer')
        pdf = sign_request.document_file.content
        self.assertEqual(sign_request.document_hash, hashlib.sha256(pdf).hexdigest())

        with self.assertRaises(UserError):
            witness.sudo()._sign('Wanda', SIGNATURE)
        self.sign(sign_request, self.customer)
        self.assertEqual((customer.state, witness.state), ('signed', 'to_sign'))
        self.assertTrue(self.notified(sign_request, self.witness))
        self.assertEqual(sign_request.progress, '1 / 2')

        self.sign(sign_request, self.witness)
        self.assertEqual(sign_request.state, 'signed')
        self.assertTrue(sign_request.date_signed)
        signed = sign_request.signed_attachment_id.raw.content
        self.assertEqual(sign_request.signed_hash, hashlib.sha256(signed).hexdigest())
        # the tests render the reports as HTML: the signature page and the certificate follow the document
        self.assertTrue(signed.startswith(pdf))
        self.assertIn(b'Wanda Witness', signed)
        self.assertIn(b'Signature Certificate', signed)
        self.assertIn(sign_request.document_hash.encode(), signed)
        self.assertEqual(self.events(sign_request),
                         ['sent', 'invited', 'signed', 'invited', 'signed', 'completed'])
        completed = self.env['mail.message'].search([
            ('model', '=', 'sign.request'), ('res_id', '=', sign_request.id),
            ('attachment_ids', 'in', sign_request.signed_attachment_id.ids)])
        self.assertEqual(completed.partner_ids, self.customer | self.witness | self.sender.partner_id,
                         'everyone gets the signed PDF')

    def test_same_sequence_signs_together(self):
        sign_request = self.upload_request([(10, 'Customer', self.customer), (10, 'Witness', self.witness)])
        self.assertEqual(sign_request.signer_ids.mapped('state'), ['to_sign', 'to_sign'])
        self.sign(sign_request, self.witness)
        self.assertEqual(sign_request.state, 'sent')
        self.sign(sign_request, self.customer)
        self.assertEqual(sign_request.state, 'signed')

    def test_decline(self):
        sign_request = self.request_for_customer()
        signer = self.signer_of(sign_request, self.customer).sudo()
        with self.assertRaises(UserError):
            signer._decline('  ')
        with patch.object(type(self.env['res.partner']), '_on_sign_declined', create=True) as hook:
            signer._decline('The price is wrong')
        hook.assert_called_once()
        self.assertEqual(sign_request.state, 'declined')
        self.assertEqual(signer.decline_reason, 'The price is wrong')
        with self.assertRaises(UserError):
            self.sign(sign_request, self.witness)

    def test_completed_hook(self):
        with patch.object(type(self.env['res.partner']), '_on_sign_completed', create=True) as hook:
            sign_request = self.request_for_customer()
            self.sign(sign_request, self.customer)
            hook.assert_not_called()
            self.sign(sign_request, self.witness)
        hook.assert_called_once()

    def test_uploaded_pdf(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)])
        pdf = sign_request.document_file.content
        self.assertEqual(sign_request.document_hash, hashlib.sha256(pdf).hexdigest())
        self.sign(sign_request, self.customer)
        self.assertEqual(sign_request.state, 'signed')
        signed = sign_request.signed_attachment_id.raw.content
        self.assertTrue(signed.startswith(pdf), 'the document comes first, then the signature page')
        self.assertIn(b'Signature Certificate', signed)

        not_pdf = self.env['sign.request'].with_user(self.sender).create({
            'name': 'Text', 'document_file': BinaryBytes(b'hello'),
            'signer_ids': [(0, 0, {'partner_id': self.customer.id})]})
        with self.assertRaises(UserError):
            not_pdf.action_send()

    def test_send_checks(self):
        no_email = self.env['res.partner'].create({'name': 'No Email'})
        with self.assertRaises(UserError):
            self.upload_request([(10, 'Buyer', no_email)])
        nobody = self.upload_request([(10, 'Buyer', self.customer)], send=False)
        nobody.signer_ids.partner_id = False
        with self.assertRaises(UserError):
            nobody.action_send()

    def test_nothing_changes_by_hand(self):
        sign_request = self.request_for_customer()
        with self.assertRaises(UserError):
            sign_request.write({'state': 'signed'})
        with self.assertRaises(UserError):
            sign_request.signer_ids[0].write({'state': 'signed'})
        with self.assertRaises(UserError):
            sign_request.signer_ids[0].write({'partner_id': self.witness.id})
        with self.assertRaises(UserError):
            sign_request.write({'signer_ids': [(0, 0, {'partner_id': self.witness.id})]})
        with self.assertRaises(UserError):
            sign_request.log_ids[0].write({'note': 'changed'})
        with self.assertRaises(UserError):
            sign_request.sudo().log_ids[0].unlink()
        with self.assertRaises(UserError):
            self.env['sign.log'].with_user(self.sender).create({'request_id': sign_request.id, 'event': 'signed'})
        with self.assertRaises(UserError):
            sign_request.unlink()

    def test_access(self):
        sign_request = self.request_for_customer()
        with self.assertRaises(AccessError):
            sign_request.with_user(self.outsider).read(['name'])
        with self.assertRaises(AccessError):
            sign_request.signer_ids[0].with_user(self.sender).read(['access_token'])
        # a user of the backend who signs reads the request, and signs from it
        shared = self.upload_request([(10, 'Reviewer', self.outsider.partner_id), (10, 'Buyer', self.customer)])
        self.assertEqual(shared.with_user(self.outsider).name, 'Uploaded Contract')
        signer = self.signer_of(shared, self.outsider.partner_id).with_user(self.outsider)
        self.assertTrue(signer.is_me)
        self.assertEqual(signer.action_sign()['url'], signer.sudo()._get_sign_url())
        with self.assertRaises(UserError):
            self.signer_of(shared, self.customer).with_user(self.outsider).action_sign()
        with self.assertRaises(AccessError):
            sign_request.with_user(self.outsider).read(['name'])

    def test_email_code(self):
        sign_request = self.request_for_customer(email_code=True)
        signer = self.signer_of(sign_request, self.customer).sudo()
        with self.assertRaisesRegex(UserError, 'code'):
            signer._sign('Acme', SIGNATURE)
        with patch.object(type(signer), '_generate_code', return_value='123456'):
            self.assertTrue(signer._send_code())
            self.assertFalse(signer._send_code(), 'one code a minute')
        self.assertFalse(signer._verify_code('000000'))
        self.assertTrue(signer._verify_code(' 123456 '))
        self.assertFalse(signer._verify_code('123456'), 'a code is used once')
        signer._sign('Acme', SIGNATURE)
        self.assertTrue(signer.code_verified)
        self.assertEqual(self.events(sign_request, signer),
                         ['invited', 'code_sent', 'code_failed', 'code_verified', 'signed'])

    def test_email_code_attempts(self):
        signer = self.signer_of(self.request_for_customer(email_code=True), self.customer).sudo()
        with patch.object(type(signer), '_generate_code', return_value='123456'):
            signer._send_code()
        for _attempt in range(5):
            self.assertFalse(signer._verify_code('999999'))
        self.assertFalse(signer._verify_code('123456'), 'too many wrong codes: a new one is needed')
        with freeze_time(fields.Datetime.now() + timedelta(minutes=11)):
            with patch.object(type(signer), '_generate_code', return_value='654321'):
                signer._send_code()
            self.assertTrue(signer._verify_code('654321'))

    def test_reminders_and_expiry(self):
        sign_request = self.request_for_customer()
        signer = self.signer_of(sign_request, self.customer)
        Request = self.env['sign.request']
        with freeze_time(fields.Datetime.now() + timedelta(days=2)):
            Request._cron_remind_and_expire()
        self.assertFalse(signer.date_reminded)
        with freeze_time(fields.Datetime.now() + timedelta(days=3, hours=1)):
            Request._cron_remind_and_expire()
        self.assertTrue(signer.date_reminded)
        self.assertEqual(self.events(sign_request, signer), ['invited', 'reminded'])
        with freeze_time(fields.Date.today() + timedelta(days=15)):
            Request._cron_remind_and_expire()
        self.assertEqual(sign_request.state, 'expired')
        with self.assertRaises(UserError):
            self.sign(sign_request, self.customer)

    def test_cancel(self):
        sign_request = self.request_for_customer()
        sign_request.action_cancel()
        self.assertEqual(sign_request.state, 'cancelled')
        self.assertIn('cancelled', self.events(sign_request))
        with self.assertRaises(UserError):
            self.sign(sign_request, self.customer)
        with self.assertRaises(UserError):
            sign_request.action_cancel()

    def test_mixin_record_request(self):
        sign_request = self.env['sign.request'].with_user(self.sender)._create_for_record(self.customer)
        self.assertEqual((sign_request.res_model, sign_request.res_id), ('res.partner', self.customer.id))
        self.assertEqual(sign_request.name, 'Acme Buyer')
        self.assertFalse(sign_request.signer_ids)
