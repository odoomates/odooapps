import base64
from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class BatchPaymentCommon(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = cls.company_data['default_journal_bank']
        cls.layout = cls.env.ref('om_account_batch_payment.batch_layout_generic_csv')
        for partner, number in ((cls.partner_a, 'GB29NWBK60161331926819'), (cls.partner_b, 'GB94BARC10201530093459')):
            partner.bank_ids = [Command.create({
                'acc_number': number,
                'allow_out_payment': True,
                'bank_id': cls.env['res.bank'].create({'name': 'Bank of %s' % partner.name, 'bic': 'NWBKGB2L'}).id,
            })]

    def _bill(self, amount, partner=None, move_type='in_invoice'):
        return self.init_invoice(move_type, partner=partner or self.partner_a, amounts=[amount], taxes=[],
                                 invoice_date='2026-03-01', post=True)

    def _pay(self, moves, journal=None, **values):
        return self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=moves.ids).create({
            'journal_id': (journal or self.bank).id,
            'payment_date': date(2026, 3, 15),
            **values,
        })._create_payments()

    def _batch(self, *amounts, partner=None):
        payments = self.env['account.payment']
        for amount in amounts:
            payments |= self._pay(self._bill(amount, partner=partner))
        action = payments.action_create_batch_payment()
        return self.env['account.batch.payment'].browse(action['res_id'])


@tagged('post_install', '-at_install')
class TestBatchPayment(BatchPaymentCommon):

    def test_create_batch_from_payments(self):
        batch = self._batch(600.0, 400.0)
        self.assertEqual(batch.state, 'draft')
        self.assertEqual(batch.batch_type, 'outbound')
        self.assertTrue(batch.name.startswith('BATCH/OUT/'))
        self.assertEqual(batch.payment_count, 2)
        self.assertAlmostEqual(batch.amount, 1000.0)
        self.assertEqual(batch.payment_method_line_id, batch.payment_ids.payment_method_line_id)

    def test_refuse_mixed_payments(self):
        other_bank = self.env['account.journal'].create({'name': 'Second Bank', 'type': 'bank', 'code': 'BNK2'})
        payments = self._pay(self._bill(100.0)) | self._pay(self._bill(200.0), journal=other_bank)
        with self.assertRaisesRegex(UserError, 'one bank journal'):
            payments.action_create_batch_payment()

        payments = self._pay(self._bill(100.0)) | self._pay(
            self.init_invoice('out_invoice', amounts=[50.0], taxes=[], invoice_date='2026-03-01', post=True))
        with self.assertRaisesRegex(UserError, 'not both'):
            payments.action_create_batch_payment()

        batch = self._batch(300.0)
        with self.assertRaisesRegex(UserError, 'already in a batch'):
            batch.payment_ids.action_create_batch_payment()

    def test_validate_generates_the_bank_file(self):
        self.bank.om_batch_layout_id = self.layout
        batch = self._batch(1000.0, 250.5)
        self.assertEqual(batch.layout_id, self.layout)
        batch.action_validate_batch()
        self.assertEqual(batch.state, 'sent')
        self.assertTrue(all(batch.payment_ids.mapped('is_sent')))
        content = base64.b64decode(batch.export_file).decode()
        lines = content.strip().split('\r\n')
        self.assertEqual(lines[0], 'Sr No,Beneficiary Name,Beneficiary Account Number,Bank Code (BIC / IFSC),'
                                   'Amount,Currency,Payment Date,Remarks,Beneficiary Email')
        self.assertEqual(len(lines), 3)
        self.assertIn('GB29NWBK60161331926819', content)
        self.assertIn(',1000.00,', content)
        self.assertIn(',250.50,', content)
        self.assertIn('15/03/2026', content)
        self.assertEqual(batch.export_filename, batch.name.replace('/', '_') + '.csv')
        self.assertTrue(batch.message_ids.attachment_ids)

    def test_bank_account_required_by_the_layout(self):
        self.bank.om_batch_layout_id = self.layout
        batch = self._batch(100.0)
        batch.payment_ids.write({'partner_bank_id': False})
        with self.assertRaisesRegex(UserError, 'bank account of the partner'):
            batch.action_validate_batch()

    def test_excel_layout_and_cents(self):
        layout = self.layout.copy({'file_type': 'xlsx'})
        batch = self._batch(100.0)
        batch.layout_id = layout
        batch.action_validate_batch()
        self.assertTrue(base64.b64decode(batch.export_file).startswith(b'PK'))
        self.assertTrue(batch.export_filename.endswith('.xlsx'))

        layout.write({'file_type': 'csv', 'amount_in_cents': True, 'include_header': False, 'delimiter': ';'})
        content, _filename = layout._generate_file(batch)
        self.assertIn(b';10000;', content)

    def test_sent_batch_locks_its_payments(self):
        batch = self._batch(500.0)
        batch.action_validate_batch()
        payment = batch.payment_ids
        with self.assertRaisesRegex(UserError, 'already sent to the bank'):
            payment.amount = 450.0
        payment.memo = payment.memo  # the same value is not a change
        batch.action_draft()
        self.assertEqual(batch.state, 'draft')
        self.assertFalse(payment.is_sent)
        payment.action_draft()
        payment.amount = 450.0
        self.assertAlmostEqual(batch.amount, 450.0)

    def test_draft_payments_posted_and_rejected_ignored(self):
        draft = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_b.id,
            'amount': 75.0,
            'journal_id': self.bank.id,
            'partner_bank_id': self.partner_b.bank_ids.id,
        })
        batch = self._batch(100.0)
        batch.payment_ids |= draft
        self.assertAlmostEqual(batch.amount, 175.0)
        batch.action_validate_batch()
        self.assertEqual(draft.state, 'in_process')

        draft.action_reject()
        self.assertAlmostEqual(batch.amount, 100.0)
        self.assertEqual(batch.payment_count, 1)

    def test_only_draft_batch_deleted(self):
        batch = self._batch(100.0)
        payments = batch.payment_ids
        batch.action_validate_batch()
        with self.assertRaisesRegex(UserError, 'draft batch'):
            batch.unlink()
        batch.action_draft()
        batch.unlink()
        self.assertFalse(payments.batch_payment_id)

    def test_register_payment_creates_the_batch(self):
        bills = self._bill(100.0) | self._bill(200.0, partner=self.partner_b)
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=bills.ids).create({
            'journal_id': self.bank.id,
            'payment_date': date(2026, 3, 15),
            'group_payment': False,
            'om_create_batch': True,
        })
        action = wizard.action_create_payments()
        self.assertEqual(action['res_model'], 'account.batch.payment')
        batch = self.env['account.batch.payment'].browse(action['res_id'])
        self.assertEqual(batch.payment_count, 2)
        self.assertEqual(batch.payment_ids.reconciled_bill_ids, bills)

    def test_deposit_and_report(self):
        invoices = (self.init_invoice('out_invoice', amounts=[300.0], taxes=[], invoice_date='2026-03-01', post=True)
                    | self.init_invoice('out_invoice', partner=self.partner_b, amounts=[200.0], taxes=[],
                                        invoice_date='2026-03-01', post=True))
        payments = self._pay(invoices[0]) | self._pay(invoices[1])
        batch = self.env['account.batch.payment'].browse(payments.action_create_batch_payment()['res_id'])
        self.assertEqual(batch.batch_type, 'inbound')
        self.assertTrue(batch.name.startswith('BATCH/IN/'))
        self.assertFalse(batch.layout_id)
        batch.action_validate_batch()
        self.assertFalse(batch.export_file)
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_batch_payment.action_report_batch_payment', batch.ids)[0].decode()
        self.assertIn('Deposit Slip', html)
        self.assertIn(self.partner_b.name, html)
