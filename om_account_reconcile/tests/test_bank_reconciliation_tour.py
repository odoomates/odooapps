from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingHttpCommon


@tagged('post_install', '-at_install')
class TestBankReconciliationTour(AccountTestInvoicingHttpCommon):

    def test_bank_reconciliation_screen(self):
        self.env.company.om_reconcile_auto = False
        bank_journal = self.company_data['default_journal_bank']
        # the screen opens on the first bank or cash journal
        bank_journal.sequence = 0
        partner = self.env['res.partner'].create({'name': 'Tour Customer'})
        invoice = self.init_invoice('out_invoice', partner=partner, amounts=[420.0], taxes=[],
                                    invoice_date='2026-01-10', post=True)
        charges = self.env['account.account'].create({
            'code': 'TOURFEE', 'name': 'Tour Bank Charges', 'account_type': 'expense',
        })
        payment = self.env['account.bank.statement.line'].create({
            'journal_id': bank_journal.id, 'date': '2026-01-20', 'amount': 420.0,
            'payment_ref': 'TOUR PAYMENT %s' % invoice.name,
        })
        fee = self.env['account.bank.statement.line'].create({
            'journal_id': bank_journal.id, 'date': '2026-01-21', 'amount': -7.0, 'payment_ref': 'Tour bank fee',
        })

        self.start_tour('/odoo/action-om_account_reconcile.action_bank_reconciliation',
                        'om_bank_reconciliation_tour', login=self.env.user.login)

        self.assertTrue(payment.is_reconciled)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        # the fee was reconciled with the counterpart, then its reconciliation undone
        self.assertFalse(fee.is_reconciled)
        self.assertFalse(self.env['account.move.line'].search_count([('account_id', '=', charges.id)]))
