from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.binary import BinaryBytes

from .common import blank_pdf


@tagged('post_install', '-at_install')
class TestMultiCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Sign Company B'})
        both = cls.company_a | cls.company_b
        # sends in both companies, then works in the first one only
        cls.sender = new_test_user(cls.env, 'om_mc_sign_sender', groups='base.group_user,om_sign.group_sign_user',
                                   email='mc.sender@example.com', company_id=cls.company_a.id,
                                   company_ids=[Command.set(both.ids)])
        cls.signer = cls.env['res.partner'].create({'name': 'Signer', 'email': 'mc.signer@example.com'})

    def request(self, company, **values):
        return self.env['sign.request'].create({
            'name': 'Contract', 'company_id': company.id, 'requested_by_id': self.sender.id,
            'document_file': BinaryBytes(blank_pdf()), 'document_filename': 'contract.pdf',
            'signer_ids': [Command.create({'partner_id': self.signer.id})], **values})

    def test_requests_signers_and_evidence(self):
        sign_request = self.request(self.company_b)
        sign_request.action_send()
        signer, logs = sign_request.signer_ids, sign_request.log_ids
        self.assertEqual(signer.company_id, self.company_b, 'the signer follows the request')
        self.assertEqual(logs.company_id, self.company_b, 'the evidence follows the request')
        in_a = self.env(user=self.sender, context=dict(self.env.context, allowed_company_ids=self.company_a.ids))
        self.assertFalse(in_a['sign.request'].search([('id', '=', sign_request.id)]))
        self.assertFalse(in_a['sign.request.signer'].search([('id', '=', signer.id)]))
        self.assertFalse(in_a['sign.log'].search([('id', 'in', logs.ids)]))
        with self.assertRaises(AccessError):
            sign_request.with_env(in_a).read(['name'])
        in_b = self.env(user=self.sender, context=dict(self.env.context, allowed_company_ids=self.company_b.ids))
        self.assertEqual(in_b['sign.request'].search([('id', '=', sign_request.id)]), sign_request)
