from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCashFlow(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.bank = cls.bank_journal.default_account_id
        cls.bank_2 = cls.env['account.journal'].create({'name': 'Second Bank', 'code': 'BNK2', 'type': 'bank'}).default_account_id
        cls.transit = cls.bank_journal.suspense_account_id
        Account = cls.env['account.account']
        cls.equipment = Account.create({'code': 'EQUIP', 'name': 'Equipment', 'account_type': 'asset_fixed'})
        cls.loan = Account.create({'code': 'LOAN', 'name': 'Bank Loan', 'account_type': 'liability_non_current'})
        cls.capital = Account.create({'code': 'CAPITAL', 'name': 'Capital', 'account_type': 'equity'})
        cls.dividends = Account.create({
            'code': 'DIVREC', 'name': 'Dividends Received', 'account_type': 'income_other', 'cash_flow_activity': 'investing',
        })

    def _entry(self, date, *lines, journal=None):
        move = self.env['account.move'].create({
            'journal_id': (journal or self.company_data['default_journal_misc']).id,
            'date': date,
            'line_ids': [Command.create({'name': 'line', 'account_id': account.id, 'balance': balance, **values})
                         for account, balance, values in lines],
        })
        move.action_post()
        return move

    def _cash_flow(self, **form):
        wizard = self.env['account.cash.flow.report'].create({
            'date_from': '2026-01-01', 'date_to': '2026-12-31', **form,
        })
        data = {'form': wizard.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id', 'display_detail'])[0]}
        return wizard, self.env['report.accounting_pdf_reports.report_cash_flow']._get_report_values(wizard.ids, data)

    @staticmethod
    def _lines(cash_flow):
        return {(section['activity'], line['key']): line['amount']
                for section in cash_flow['sections'] for line in section['lines']}

    def test_cash_flow_statement(self):
        receivable = self.company_data['default_account_receivable']
        payable = self.company_data['default_account_payable']
        # opening cash
        self._entry('2025-12-31', (self.bank, 10000.0, {}), (self.capital, -10000.0, {}))

        # a customer invoice paid through the transit account, matched to the bank
        invoice = self.init_invoice('out_invoice', amounts=[1000.0], taxes=[], invoice_date='2026-02-01', post=True)
        payment = self._entry('2026-02-10', (self.transit, 1000.0, {}),
                              (receivable, -1000.0, {'partner_id': invoice.partner_id.id}))
        (invoice.line_ids | payment.line_ids).filtered(lambda line: line.account_id == receivable).reconcile()
        bank_receipt = self._entry('2026-02-11', (self.bank, 1000.0, {}), (self.transit, -1000.0, {}), journal=self.bank_journal)
        (payment.line_ids | bank_receipt.line_ids).filtered(lambda line: line.account_id == self.transit).reconcile()

        # a bill paid straight from the bank
        bill = self.init_invoice('in_invoice', amounts=[400.0], taxes=[], invoice_date='2026-03-01', post=True)
        bill_payment = self._entry('2026-03-05', (self.bank, -400.0, {}),
                                   (payable, 400.0, {'partner_id': bill.partner_id.id}), journal=self.bank_journal)
        (bill.line_ids | bill_payment.line_ids).filtered(lambda line: line.account_id == payable).reconcile()

        # equipment, a loan, dividends received, a transfer between banks and a receipt not matched yet
        self._entry('2026-04-01', (self.bank, -5000.0, {}), (self.equipment, 5000.0, {}), journal=self.bank_journal)
        self._entry('2026-05-01', (self.bank, 3000.0, {}), (self.loan, -3000.0, {}), journal=self.bank_journal)
        self._entry('2026-06-01', (self.bank, 250.0, {}), (self.dividends, -250.0, {}), journal=self.bank_journal)
        self._entry('2026-07-01', (self.bank, -200.0, {}), (self.bank_2, 200.0, {}), journal=self.bank_journal)
        self._entry('2026-08-01', (self.bank, 60.0, {}), (self.transit, -60.0, {}), journal=self.bank_journal)
        # a draft entry only counts with all the entries
        draft = self.env['account.move'].create({
            'journal_id': self.bank_journal.id, 'date': '2026-09-01',
            'line_ids': [Command.create({'name': 'draft', 'account_id': self.bank.id, 'balance': 70.0}),
                         Command.create({'name': 'draft', 'account_id': self.loan.id, 'balance': -70.0})],
        })

        wizard, values = self._cash_flow()
        cash_flow = values['cash_flow']
        self.assertEqual(self._lines(cash_flow), {
            ('operating', 'receivable'): 1000.0,
            ('operating', 'payable'): -400.0,
            ('operating', 'unmatched'): 60.0,
            ('investing', 'fixed_asset'): -5000.0,
            ('investing', 'income'): 250.0,
            ('financing', 'borrowing'): 3000.0,
        })
        self.assertEqual(cash_flow['opening'], 10000.0)
        self.assertEqual(cash_flow['net_change'], -1090.0)
        self.assertEqual(cash_flow['closing'], 8910.0)
        self.assertEqual(sum(section['total'] for section in cash_flow['sections']), cash_flow['net_change'])

        _wizard, values = self._cash_flow(target_move='all', display_detail='accounts')
        self.assertEqual(self._lines(values['cash_flow'])[('financing', 'borrowing')], 3070.0)
        self.assertEqual(values['cash_flow']['closing'], 8980.0)
        self.assertTrue(draft)

        html = self.env['ir.actions.report']._render_qweb_html(
            'accounting_pdf_reports.report_cash_flow', wizard.ids,
            data={'form': wizard.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id', 'display_detail'])[0]},
        )[0].decode()
        self.assertIn('Cash Flow Statement', html)
        self.assertIn('Cash received from customers', html)

    def test_print_action(self):
        wizard = self.env['account.cash.flow.report'].create({'date_from': '2026-01-01', 'date_to': '2026-12-31'})
        action = wizard.with_context(discard_logo_check=True).check_report()
        self.assertEqual(action['report_name'], 'accounting_pdf_reports.report_cash_flow')
        wizard.date_from = '2027-01-01'
        with self.assertRaises(UserError):
            wizard.check_report()
