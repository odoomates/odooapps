from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.om_account_batch_payment.tests.test_batch_payment import BatchPaymentCommon


@tagged('post_install', '-at_install')
class TestBatchReconcile(BatchPaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.om_reconcile_auto = False

    def _transaction(self, amount, label='Transfer'):
        return self.env['account.bank.statement.line'].create({
            'journal_id': self.bank.id,
            'date': '2026-03-17',
            'payment_ref': label,
            'amount': amount,
        })

    def _sent_batch(self, *amounts, partner=None):
        batch = self._batch(*amounts, partner=partner)
        batch.action_validate_batch()
        return batch

    def _without_outstanding_account(self):
        """ Payments without journal entry, as with the In Payment status of the invoices that
        om_account_accountant keeps: without it, Odoo gives every payment an outstanding account. """
        self.startPatcher(patch.object(
            self.env.registry['account.move'], '_get_invoice_in_payment_state', lambda self: 'in_payment'))
        method_lines = self.bank.inbound_payment_method_line_ids | self.bank.outbound_payment_method_line_ids
        method_lines.payment_account_id = False

    def test_batch_suggested_by_its_reference(self):
        batch = self._sent_batch(600.0, 400.0)
        st_line = self._transaction(-1000.0, label='BULK %s' % batch.name)
        data = st_line.om_bank_rec_get_data()
        self.assertEqual(data['suggestion']['batch_name'], batch.name)
        self.assertEqual(len(data['suggestion']['matches']), 2)
        self.assertEqual(set(data['suggestion']['batch_payment_ids']), set(batch.payment_ids.ids))

        st_line._om_reconcile(st_line._om_clean_proposal(data['suggestion']))
        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(all(batch.payment_ids.mapped('om_is_cleared')))
        self.assertEqual(batch.state, 'reconciled')
        self.assertEqual(batch.statement_line_ids, st_line)

        st_line.action_undo_reconciliation()
        self.assertFalse(any(batch.payment_ids.mapped('om_is_cleared')))
        self.assertEqual(batch.state, 'sent')

    def test_batch_suggested_by_its_amount(self):
        batch = self._sent_batch(150.0, 350.0)
        st_line = self._transaction(-500.0)
        self.assertEqual(st_line._om_suggested_proposal()['batch_payment_ids'], batch.payment_ids.ids)
        batches = st_line.om_bank_rec_batches()
        self.assertEqual([item['id'] for item in batches], batch.ids)
        self.assertEqual(batches[0]['amount'], 500.0)
        self.assertEqual(batches[0]['score'], 50)
        # a deposit is not offered for money going out
        self.assertFalse(self._transaction(500.0).om_bank_rec_batches())

    def test_two_batches_of_the_same_amount_are_not_guessed(self):
        self._sent_batch(200.0)
        self._sent_batch(200.0)
        st_line = self._transaction(-200.0)
        self.assertFalse(st_line._om_suggested_proposal())
        self.assertEqual(len(st_line.om_bank_rec_batches()), 2)

    def test_payments_without_journal_entry(self):
        self._without_outstanding_account()
        bill_1, bill_2 = self._bill(700.0), self._bill(300.0)
        payments = self._pay(bill_1) | self._pay(bill_2)
        self.assertFalse(payments.move_id)
        batch = self.env['account.batch.payment'].browse(payments.action_create_batch_payment()['res_id'])
        batch.action_validate_batch()
        self.assertEqual(batch.state, 'sent')

        st_line = self._transaction(-1000.0, label=batch.name)
        proposal = st_line._om_batch_proposal(batch)
        open_lines = (bill_1 | bill_2).line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable')
        self.assertEqual({match['aml_id'] for match in proposal['matches']}, set(open_lines.ids))
        self.assertFalse(proposal['writeoffs'])
        self.assertTrue(st_line._om_is_complete(proposal))

        st_line._om_reconcile(proposal)
        self.assertEqual(set(payments.mapped('state')), {'paid'})
        self.assertEqual(set((bill_1 | bill_2).mapped('payment_state')) - {'in_payment'}, {'paid'})
        self.assertEqual(batch.state, 'reconciled')

        st_line.action_undo_reconciliation()
        self.assertEqual(set(payments.mapped('state')), {'in_process'})
        self.assertEqual(batch.state, 'sent')

    def test_payment_without_journal_entry_nor_invoice(self):
        self._without_outstanding_account()
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_a.id,
            'amount': 250.0,
            'journal_id': self.bank.id,
            'partner_bank_id': self.partner_a.bank_ids.id,
        })
        payment.action_post()
        batch = self.env['account.batch.payment'].browse(payment.action_create_batch_payment()['res_id'])
        batch.action_validate_batch()

        st_line = self._transaction(-250.0)
        proposal = st_line._om_suggested_proposal()
        self.assertEqual(len(proposal['writeoffs']), 1)
        writeoff = proposal['writeoffs'][0]
        self.assertEqual(writeoff['account_id'], payment.destination_account_id.id)
        self.assertEqual(writeoff['amount'], 250.0)
        st_line._om_reconcile(proposal)
        self.assertEqual(payment.state, 'paid')
        payable = st_line.move_id.line_ids.filtered(lambda line: line.account_id == payment.destination_account_id)
        self.assertEqual((payable.partner_id, payable.balance), (self.partner_a, 250.0))

    def test_bank_clearing_part_of_the_batch(self):
        self._without_outstanding_account()
        batch = self._sent_batch(600.0, 400.0)
        st_line = self._transaction(-600.0)
        st_line._om_reconcile(st_line._om_batch_proposal(batch))
        self.assertTrue(st_line.is_reconciled)
        # the bank paid less than the batch: the payment it covers whole is paid, the other one is not guessed
        first, second = batch.payment_ids.sorted('amount', reverse=True)
        self.assertEqual((first.state, second.state), ('paid', 'in_process'))
        self.assertEqual(batch.state, 'sent')
        self.assertIn('part of the batch', batch.message_ids[0].body)

    def test_automatic_reconciliation(self):
        self.env.company.om_reconcile_auto = True
        batch = self._sent_batch(120.0, 80.0)
        st_line = self._transaction(-200.0, label='Payment run %s' % batch.name)
        self.assertEqual(st_line._om_auto_reconcile(), st_line)
        self.assertEqual(batch.state, 'reconciled')

    def test_screen_proposal_of_a_batch(self):
        batch = self._sent_batch(100.0)
        st_line = self._transaction(-100.0, label='Unrelated label')
        proposal = st_line.om_bank_rec_batch_proposal(batch.id)
        self.assertEqual(proposal['matches'][0]['candidate']['id'], proposal['matches'][0]['aml_id'])
        self.assertEqual(proposal['matches'][0]['payment_ids'], batch.payment_ids.ids)
        cleaned = st_line._om_clean_proposal({**proposal, 'batch_payment_ids': batch.payment_ids.ids})
        st_line.om_bank_rec_validate(cleaned)
        self.assertEqual(st_line.om_batch_payment_ids, batch.payment_ids)
        self.assertEqual(batch.state, 'reconciled')
