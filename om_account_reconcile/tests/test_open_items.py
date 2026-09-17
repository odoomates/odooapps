from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestOpenItems(AccountTestInvoicingCommon):
    """ Clearing an invoice against what settles it, without any transaction of the bank.

    A cash payment, a credit note or a refund never reaches a bank statement, so the bank reconciliation
    cannot clear them: the open items do.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.line_model = cls.env['account.move.line']
        cls.receivable = cls.company_data['default_account_receivable']

    def _invoice(self, amount, post=True):
        return self.init_invoice('out_invoice', amounts=[amount], invoice_date='2026-06-01',
                                 taxes=[], post=post, partner=self.partner_a)

    def _cash_payment(self, amount):
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_a.id,
            'amount': amount,
            'date': '2026-06-05',
            'journal_id': self.company_data['default_journal_cash'].id,
        })
        payment.action_post()
        return payment

    def _groups(self, **kwargs):
        return self.line_model.om_open_items_search_groups(**kwargs)['groups']

    def _partner_group(self):
        return next(group for group in self._groups(account_type='receivable')
                    if group['partner_id'] == self.partner_a.id)

    def test_the_partner_shows_what_is_left_to_clear(self):
        self._invoice(200.0)
        self._cash_payment(50.0)
        group = self._partner_group()
        self.assertEqual(group['account_id'], self.receivable.id)
        self.assertEqual(group['count'], 2, 'the invoice and the payment are both open')
        self.assertAlmostEqual(group['residual'], 150.0, msg='what the customer still owes')

    def test_the_items_of_the_partner_are_listed(self):
        self._invoice(200.0)
        self._cash_payment(50.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        self.assertEqual(len(data['lines']), 2)
        self.assertAlmostEqual(data['debit'], 200.0)
        self.assertAlmostEqual(data['credit'], 50.0)
        self.assertAlmostEqual(data['clearable'], 50.0, msg='only the smaller side can be cleared')

    def test_reconciling_a_payment_with_its_invoice(self):
        invoice = self._invoice(200.0)
        payment = self._cash_payment(200.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        self.line_model.om_open_items_reconcile([line['id'] for line in data['lines']])
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertTrue(all(payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.receivable).mapped('reconciled')))
        self.assertFalse([group for group in self._groups(account_type='receivable')
                          if group['partner_id'] == self.partner_a.id],
                         'nothing is left to clear for the customer')

    def test_a_partial_payment_leaves_the_rest_open(self):
        invoice = self._invoice(200.0)
        self._cash_payment(50.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        self.line_model.om_open_items_reconcile([line['id'] for line in data['lines']])
        self.assertEqual(invoice.payment_state, 'partial')
        self.assertAlmostEqual(invoice.amount_residual, 150.0)

    def test_items_all_on_the_same_side_are_refused(self):
        """ Two invoices settle nothing: something has to be there to settle them. """
        self._invoice(200.0)
        self._invoice(300.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        with self.assertRaises(UserError):
            self.line_model.om_open_items_reconcile([line['id'] for line in data['lines']])

    def test_a_payment_larger_than_the_invoice_leaves_a_credit(self):
        """ The other way round: what is left over stays open for the next invoice. """
        invoice = self._invoice(200.0)
        self._cash_payment(500.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        self.line_model.om_open_items_reconcile([line['id'] for line in data['lines']])
        self.assertEqual(invoice.payment_state, 'paid')
        group = self._partner_group()
        self.assertAlmostEqual(group['residual'], -300.0, msg='the customer has 300 to its credit')

    def test_writing_the_rest_off_closes_the_invoice(self):
        """ The customer paid 190 of a 200 invoice and the 10 is given up: the invoice is settled. """
        invoice = self._invoice(200.0)
        self._cash_payment(190.0)
        discount = self.env['account.account'].create({
            'code': 'DISCGIVEN', 'name': 'Discount Given', 'account_type': 'expense',
        })
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        self.line_model.om_open_items_reconcile(
            [line['id'] for line in data['lines']],
            writeoff={
                'account_id': discount.id,
                'journal_id': self.company_data['default_journal_misc'].id,
                'label': 'Early payment discount',
            },
        )
        self.assertEqual(invoice.payment_state, 'paid', 'nothing is left on the invoice')
        self.assertFalse([group for group in self._groups(account_type='receivable')
                          if group['partner_id'] == self.partner_a.id],
                         'the customer has nothing open any more')
        written_off = self.env['account.move.line'].search([
            ('account_id', '=', discount.id), ('name', '=', 'Early payment discount'),
        ])
        self.assertAlmostEqual(sum(written_off.mapped('balance')), 10.0,
                               msg='what was given up is on the account chosen for it')

    def test_one_item_alone_is_refused(self):
        self._invoice(200.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        with self.assertRaises(UserError):
            self.line_model.om_open_items_reconcile([data['lines'][0]['id']])

    def test_the_oldest_items_that_cancel_out_are_suggested(self):
        """ What an accountant picks: the oldest invoice and the payment that covers it exactly. """
        self._invoice(200.0)
        self._invoice(300.0)
        self._cash_payment(200.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        suggested = self.line_model.browse(data['suggestion'])
        self.assertEqual(len(suggested), 2, 'the payment and the invoice it covers')
        self.assertAlmostEqual(sum(suggested.mapped('amount_residual')), 0.0,
                               msg='what is suggested clears exactly')

    def test_nothing_is_suggested_when_nothing_cancels_out(self):
        self._invoice(200.0)
        self._cash_payment(50.0)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        self.assertFalse(data['suggestion'],
                         'a difference the user did not ask for is not proposed')

    def test_a_draft_entry_is_not_open(self):
        self._invoice(200.0, post=False)
        self.assertFalse([group for group in self._groups(account_type='receivable')
                          if group['partner_id'] == self.partner_a.id],
                         'only what is posted is waiting to be cleared')

    def test_vendors_are_looked_at_apart(self):
        self._invoice(200.0)
        bill = self.init_invoice('in_invoice', amounts=[75.0], invoice_date='2026-06-01', taxes=[],
                                 post=True, partner=self.partner_a)
        receivable_groups = self._groups(account_type='receivable')
        payable_groups = self._groups(account_type='payable')
        self.assertTrue(any(group['partner_id'] == self.partner_a.id for group in receivable_groups))
        payable = next(group for group in payable_groups if group['partner_id'] == self.partner_a.id)
        self.assertAlmostEqual(payable['residual'], -75.0, msg='what is owed to the vendor')
        self.assertNotEqual(payable['account_id'], self.receivable.id,
                            'the two sides are cleared on their own account')
        self.assertEqual(bill.payment_state, 'not_paid')

    def test_searching_a_partner(self):
        self._invoice(200.0)
        groups = self._groups(account_type='receivable', search=self.partner_a.name)
        self.assertTrue(groups)
        self.assertTrue(all(group['partner_id'] == self.partner_a.id for group in groups))
        self.assertFalse(self._groups(account_type='receivable', search='no such partner here'))

    def test_searching_an_amount(self):
        self._invoice(200.0)
        self.assertTrue(self._groups(account_type='receivable', search='200'))

    def test_a_credit_note_clears_an_invoice(self):
        """ Neither reaches the bank: the open items are the only way to settle them. """
        invoice = self._invoice(200.0)
        credit_note = self.init_invoice('out_refund', amounts=[200.0], invoice_date='2026-06-10',
                                        taxes=[], post=True, partner=self.partner_a)
        group = self._partner_group()
        data = self.line_model.om_open_items_get_lines(group['partner_id'], group['account_id'])
        self.line_model.om_open_items_reconcile([line['id'] for line in data['lines']])
        # fully cleared by a credit note, the invoice is flagged as reversed rather than paid
        self.assertEqual(invoice.payment_state, 'reversed')
        self.assertEqual(credit_note.payment_state, 'paid')
