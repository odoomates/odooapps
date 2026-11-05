from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPartnerLedgerInitialBalance(AccountTestInvoicingCommon):

    def _ledger(self, **vals):
        wizard = self.env['account.report.partner.ledger'].create(dict({
            'result_selection': 'customer',
            'target_move': 'posted',
            'journal_ids': [Command.set(self.env['account.journal'].search([]).ids)],
        }, **vals))
        data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
        return self.env['report.accounting_pdf_reports.report_partnerledger']._get_report_values(None, data)

    def _invoice(self, partner, amount, day, move_type='out_invoice'):
        return self.init_invoice(move_type, partner=partner, amounts=[amount], taxes=[], invoice_date=day, post=True)

    def test_running_balance_starts_from_the_initial_balance(self):
        self._invoice(self.partner_a, 100.0, '2025-03-01')
        self._invoice(self.partner_a, 40.0, '2025-07-01')
        self._invoice(self.partner_a, 30.0, '2025-08-01', 'out_refund')

        values = self._ledger(date_from='2025-07-01', date_to='2025-12-31')
        data, sum_partner = values['data'], values['sum_partner']
        self.assertEqual(data['computed']['initial_balances'][self.partner_a.id], 100.0)
        self.assertEqual([line['progress'] for line in values['lines'](data, self.partner_a)], [140.0, 110.0])
        # debit and credit stay those of the period, the balance is the one at the end date
        self.assertEqual(sum_partner(data, self.partner_a, 'debit'), 40.0)
        self.assertEqual(sum_partner(data, self.partner_a, 'credit'), 30.0)
        self.assertEqual(sum_partner(data, self.partner_a, 'debit - credit'), 110.0)

    def test_entries_of_the_start_date_are_not_counted_twice(self):
        self._invoice(self.partner_a, 100.0, '2025-07-01')
        values = self._ledger(date_from='2025-07-01')
        self.assertFalse(values['data']['computed']['initial_balances'])
        self.assertEqual(values['sum_partner'](values['data'], self.partner_a, 'debit - credit'), 100.0)

    def test_partner_without_entries_in_the_period(self):
        """ It still owes its initial balance, unless that balance is zero. """
        self._invoice(self.partner_a, 100.0, '2025-03-01')
        self._invoice(self.partner_b, 50.0, '2025-03-01')
        self._invoice(self.partner_b, 50.0, '2025-04-01', 'out_refund')

        values = self._ledger(date_from='2025-07-01', reconciled=True)
        self.assertIn(self.partner_a, values['docs'])
        self.assertNotIn(self.partner_b, values['docs'])
        self.assertEqual(values['lines'](values['data'], self.partner_a), [])
        self.assertEqual(values['sum_partner'](values['data'], self.partner_a, 'debit - credit'), 100.0)

    def test_filters_apply_to_the_initial_balance(self):
        self._invoice(self.partner_a, 100.0, '2025-03-01')
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[70.0], taxes=[],
                          invoice_date='2025-03-01')
        paid = self._invoice(self.partner_a, 25.0, '2025-03-01')
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=paid.ids,
        ).create({'payment_date': '2025-03-02'})._create_payments()

        form = {'date_from': '2025-07-01'}
        # posted, without the entries fully reconciled
        balances = self._ledger(reconciled=False, **form)['data']['computed']['initial_balances']
        self.assertEqual(balances[self.partner_a.id], 100.0)
        # with them (the default), the paid invoice and its payment cancel out: the same balance
        balances = self._ledger(**form)['data']['computed']['initial_balances']
        self.assertEqual(balances[self.partner_a.id], 100.0)
        # with the draft invoice too
        balances = self._ledger(target_move='all', reconciled=False, **form)['data']['computed']['initial_balances']
        self.assertEqual(balances[self.partner_a.id], 170.0)

    def test_payable_side_only_with_its_filter(self):
        self._invoice(self.partner_a, 100.0, '2025-03-01')
        self._invoice(self.partner_a, 60.0, '2025-03-01', 'in_invoice')
        balances = self._ledger(date_from='2025-07-01', result_selection='supplier')['data']['computed']
        self.assertEqual(balances['initial_balances'][self.partner_a.id], -60.0)
        balances = self._ledger(date_from='2025-07-01', result_selection='customer_supplier')['data']['computed']
        self.assertEqual(balances['initial_balances'][self.partner_a.id], 40.0)

    def test_other_company_not_counted(self):
        self._invoice(self.partner_a, 100.0, '2025-03-01')
        other = self.setup_other_company()
        self.env['account.move'].with_company(other['company']).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-03-01',
            'invoice_line_ids': [Command.create({'name': 'Other', 'price_unit': 900.0, 'tax_ids': []})],
        }).action_post()
        balances = self._ledger(date_from='2025-07-01')['data']['computed']['initial_balances']
        self.assertEqual(balances[self.partner_a.id], 100.0)

    def test_without_the_option_or_a_start_date(self):
        self._invoice(self.partner_a, 100.0, '2025-03-01')
        self._invoice(self.partner_a, 40.0, '2025-07-01')

        values = self._ledger(date_from='2025-07-01', initial_balance=False)
        self.assertEqual([line['progress'] for line in values['lines'](values['data'], self.partner_a)], [40.0])
        self.assertEqual(values['sum_partner'](values['data'], self.partner_a, 'debit - credit'), 40.0)

        # without a start date the report covers the whole history, nothing is added
        values = self._ledger(date_from=False, date_to='2025-12-31')
        self.assertEqual([line['progress'] for line in values['lines'](values['data'], self.partner_a)],
                         [100.0, 140.0])

    def test_template_shows_the_row(self):
        self._invoice(self.partner_a, 100.0, '2025-03-01')
        self._invoice(self.partner_a, 40.0, '2025-07-01')

        def render(**vals):
            wizard = self.env['account.report.partner.ledger'].create(dict({
                'result_selection': 'customer', 'target_move': 'posted',
                'partner_ids': [Command.set(self.partner_a.ids)],
                'journal_ids': [Command.set(self.env['account.journal'].search([]).ids)],
            }, **vals))
            data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
            html, _type = self.env['ir.actions.report']._render_qweb_html(
                'accounting_pdf_reports.report_partnerledger', wizard.ids, data=data)
            return html.decode()

        self.assertIn('Initial Balance', render(date_from='2025-07-01'))
        self.assertNotIn('Initial Balance', render(date_from='2025-07-01', initial_balance=False))
        self.assertNotIn('Initial Balance', render(date_from=False, date_to='2025-12-31'))
