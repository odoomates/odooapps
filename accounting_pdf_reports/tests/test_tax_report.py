from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestTaxReport(AccountTestInvoicingCommon):

    def _post(self, move_type, tax, amount):
        # the accounting date set as well: the test helpers leave the date of a refund to the form
        move = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.partner_a.id,
            'invoice_date': '2025-03-10', 'date': '2025-03-10',
            'invoice_line_ids': [Command.create({'name': 'test line', 'price_unit': amount,
                                                 'tax_ids': [Command.set(tax.ids)]})],
        })
        move.action_post()
        return move

    def _tax_lines(self, date_from='2025-01-01', date_to='2025-12-31'):
        # read with SQL, like the report: it flushes in _get_report_values
        self.env.flush_all()
        lines = self.env['report.accounting_pdf_reports.report_tax'].get_lines({
            'date_from': date_from, 'date_to': date_to, 'target_move': 'posted',
            'used_context': {'company_id': self.env.company.id},
        })
        return {
            group: {line['name']: (line['net'], line['tax']) for line in group_lines}
            for group, group_lines in lines.items()
        }

    def test_refunds_are_deducted_and_both_sides_are_positive(self):
        sale_tax, purchase_tax = self.tax_sale_a, self.tax_purchase_a
        for move_type, tax, amount in (
            ('out_invoice', sale_tax, 1000.0),
            ('out_refund', sale_tax, 100.0),
            ('in_invoice', purchase_tax, 400.0),
            ('in_refund', purchase_tax, 40.0),
        ):
            self._post(move_type, tax, amount)

        lines = self._tax_lines()
        # the sales are credits and the purchases debits: both print as positive figures,
        # a refund is deducted from its side
        self.assertEqual(lines['sale'][sale_tax.name], (900.0, 135.0))
        self.assertEqual(lines['purchase'][purchase_tax.name], (360.0, 54.0))

    def test_a_period_of_refunds_stays_negative(self):
        self._post('out_refund', self.tax_sale_a, 100.0)
        self.assertEqual(self._tax_lines()['sale'][self.tax_sale_a.name], (-100.0, -15.0))

    def _pay(self, move, payment_date, **values):
        """ Pay `move` from a bank journal whose payments are entries reconciled with it """
        bank = self.company_data['default_journal_bank']
        outstanding = self.env['account.account'].create({
            'code': 'OUTST%d' % move.id, 'name': 'Outstanding', 'account_type': 'asset_current', 'reconcile': True})
        (bank.inbound_payment_method_line_ids | bank.outbound_payment_method_line_ids).payment_account_id = outstanding
        return self.env['account.payment.register'].with_context(active_model='account.move', active_ids=move.ids)\
            .create({'payment_date': payment_date, 'journal_id': bank.id, **values})._create_payments()

    def test_a_cash_basis_tax_is_due_on_its_payment(self):
        """ Invoiced in January and paid in February: the cash basis tax is in the report of February only. """
        self.env.company.tax_exigibility = True
        self.env.company.tax_cash_basis_journal_id = self.company_data['default_journal_misc']
        transition = self.env['account.account'].create({
            'code': 'CABATR', 'name': 'Tax to collect', 'account_type': 'liability_current', 'reconcile': True})
        tax = self.tax_sale_a.copy({'name': 'Cash Basis 15%', 'tax_exigibility': 'on_payment',
                                    'cash_basis_transition_account_id': transition.id})
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner_a.id, 'invoice_date': '2025-01-15',
            'date': '2025-01-15',
            'invoice_line_ids': [Command.create({'name': 'line', 'price_unit': 1000.0, 'tax_ids': [Command.set(tax.ids)]})],
        })
        invoice.action_post()
        self._pay(invoice, '2025-02-10')
        self.assertNotIn('Cash Basis 15%', self._tax_lines('2025-01-01', '2025-01-31')['sale'])
        self.assertEqual(self._tax_lines('2025-02-01', '2025-02-28')['sale']['Cash Basis 15%'], (1000.0, 150.0))

    def test_a_withholding_tax_is_counted_once_and_apart(self):
        """ With l10n_account_withholding_tax: the tax withheld on a payment is in a section of its own, its
        base counted once, on the payment, not on the bill too. """
        if 'is_withholding_tax_on_payment' not in self.env['account.tax']._fields:
            self.skipTest('l10n_account_withholding_tax is not installed')
        self.env.company.withholding_tax_base_account_id = self.env['account.account'].create({
            'code': 'WITHB', 'name': 'Withholding Tax Base', 'account_type': 'asset_current'})
        sequence = self.env['ir.sequence'].create({'implementation': 'no_gap', 'name': 'Withholding', 'padding': 4})
        withholding = self.tax_purchase_a.copy({
            'name': 'Withholding 5%', 'amount': -5, 'is_withholding_tax_on_payment': True, 'withholding_sequence_id': sequence.id})
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.partner_a.id, 'invoice_date': '2025-06-01',
            'date': '2025-06-01',
            'invoice_line_ids': [Command.create({'name': 'line', 'price_unit': 1000.0,
                                                 'tax_ids': [Command.set((self.tax_purchase_a | withholding).ids)]})],
        })
        bill.action_post()
        self._pay(bill, '2025-06-20')
        lines = self._tax_lines('2025-06-01', '2025-06-30')
        self.assertEqual(lines['withholding']['Withholding 5%'], (1000.0, 50.0))
        self.assertEqual(lines['purchase'][self.tax_purchase_a.name], (1000.0, 150.0))
        self.assertNotIn('Withholding 5%', lines['purchase'])
