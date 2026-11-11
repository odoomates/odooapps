from datetime import date

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingHttpCommon


@tagged('post_install', '-at_install')
class TestBatchReconciliationTour(AccountTestInvoicingHttpCommon):

    def _batch(self, *amounts):
        payments = self.env['account.payment']
        for amount in amounts:
            bill = self.init_invoice('in_invoice', amounts=[amount], taxes=[], invoice_date='2026-03-01', post=True)
            payments |= self.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=bill.ids).create({
                'journal_id': self.bank_journal.id,
                'payment_date': date(2026, 3, 15),
            })._create_payments()
        batch = self.env['account.batch.payment'].browse(payments.action_create_batch_payment()['res_id'])
        batch.action_validate_batch()
        return batch

    def test_batch_in_the_reconciliation_screen(self):
        self.env.company.om_reconcile_auto = False
        self.bank_journal = self.company_data['default_journal_bank']
        # the screen opens on the first bank or cash journal
        self.bank_journal.sequence = 0
        batches = self._batch(600.0, 400.0) | self._batch(300.0, 700.0)
        st_line = self.env['account.bank.statement.line'].create({
            'journal_id': self.bank_journal.id, 'date': '2026-03-17', 'amount': -1000.0, 'payment_ref': 'TOUR RUN',
        })

        self.start_tour('/odoo/action-om_account_reconcile.action_bank_reconciliation',
                        'om_batch_reconciliation_tour', login=self.env.user.login)

        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(sorted(batches.mapped('state')), ['reconciled', 'sent'])
        self.assertEqual(st_line.om_batch_payment_ids.batch_payment_id.state, 'reconciled')
