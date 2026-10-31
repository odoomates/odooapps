import base64
from datetime import date

from odoo import Command

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class LoanCommon(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.long_term_account = Account.create({
            'code': '171900', 'name': 'Bank Loans (non-current)', 'account_type': 'liability_non_current'})
        cls.short_term_account = Account.create({
            'code': '161900', 'name': 'Bank Loans (current)', 'account_type': 'liability_current'})
        cls.interest_account = Account.create({
            'code': '661900', 'name': 'Interest on Loans', 'account_type': 'expense'})
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.misc_journal = cls.company_data['default_journal_misc']
        cls.outstanding_receipts = cls.inbound_payment_method_line.payment_account_id
        cls.outstanding_payments = cls.outbound_payment_method_line.payment_account_id
        cls.env.company.write({
            'loan_long_term_account_id': cls.long_term_account.id,
            'loan_short_term_account_id': cls.short_term_account.id,
            'loan_interest_account_id': cls.interest_account.id,
            'loan_journal_id': cls.misc_journal.id,
            'loan_bank_journal_id': cls.bank_journal.id,
        })
        cls.lender = cls.env['res.partner'].create({'name': 'Test Bank', 'is_company': True})
        # leases
        cls.lease_long_term_account = Account.create({
            'code': '172900', 'name': 'Lease Liabilities (non-current)', 'account_type': 'liability_non_current'})
        cls.lease_short_term_account = Account.create({
            'code': '162900', 'name': 'Lease Liabilities (current)', 'account_type': 'liability_current'})
        cls.rou_account = Account.create({
            'code': '152900', 'name': 'Right-of-use Assets', 'account_type': 'asset_non_current'})
        cls.purchase_journal = cls.company_data['default_journal_purchase']
        cls.env.company.write({
            'lease_long_term_account_id': cls.lease_long_term_account.id,
            'lease_short_term_account_id': cls.lease_short_term_account.id,
            'lease_rou_account_id': cls.rou_account.id,
            'lease_bill_journal_id': cls.purchase_journal.id,
        })
        cls.lessor = cls.env['res.partner'].create({'name': 'Test Properties', 'is_company': True})
        # a withholding tax of 1% on the interest, as the P.N.D. 53 of Thailand
        cls.withholding_account = Account.create({
            'code': '213900', 'name': 'Withholding Tax Payable', 'account_type': 'liability_current'})
        cls.withholding_tax = cls._create_withholding_tax(-1.0)
        cls.vat_account = Account.create({
            'code': '114900', 'name': 'Input VAT on Leases', 'account_type': 'asset_current'})
        cls.vat_tax = cls._create_withholding_tax(7.0, name='Lease VAT 7%', account=cls.vat_account)

    @classmethod
    def _create_withholding_tax(cls, amount, name='WHT 1% interest', account=None):
        """ A purchase tax of `amount` % booked on `account`, the withholding tax account by default. """
        account = account or cls.withholding_account

        def repartition():
            return [
                Command.create({'repartition_type': 'base'}),
                Command.create({'repartition_type': 'tax', 'account_id': account.id}),
            ]
        return cls.env['account.tax'].create({
            'name': name,
            'amount_type': 'percent',
            'amount': amount,
            'type_tax_use': 'purchase',
            'invoice_repartition_line_ids': repartition(),
            'refund_repartition_line_ids': repartition(),
        })

    @classmethod
    def _create_lease(cls, confirm=True, **vals):
        """ 12 monthly lease payments of 1,000.00 in arrears at 6%: a liability of 11,618.93. """
        lease = cls.env['account.loan'].create({
            'loan_type': 'lease',
            'partner_id': cls.lessor.id,
            'lease_payment': 1000.0,
            'date_start': date(2025, 1, 1),
            'date_first_payment': date(2025, 2, 1),
            'payment_count': 12,
            'rate': 6.0,
            'bill_auto_create': False,
            **vals,
        })
        if confirm:
            lease.action_confirm()
        return lease

    @classmethod
    def _import(cls, loan, content, filename='schedule.csv', columns='principal'):
        if isinstance(content, str):
            content = content.encode()
        wizard = cls.env['account.loan.import'].create({
            'loan_id': loan.id, 'file': base64.b64encode(content), 'filename': filename, 'columns': columns})
        wizard.action_import()
        return wizard

    @classmethod
    def _create_loan(cls, confirm=True, **vals):
        loan = cls.env['account.loan'].create({
            'partner_id': cls.lender.id,
            'principal': 100000.0,
            'date_start': date(2025, 1, 1),
            'date_first_payment': date(2025, 2, 1),
            'payment_count': 12,
            'rate': 6.0,
            **vals,
        })
        if confirm:
            loan.action_confirm()
        return loan

    @classmethod
    def _draw(cls, loan, day=None, amount=None, **vals):
        wizard = cls.env['account.loan.drawdown'].create({
            'loan_id': loan.id, 'date': day or loan.date_start, **({'amount': amount} if amount else {}), **vals})
        wizard.action_confirm()
        return loan.operation_ids.filtered(lambda op: op.operation_type == 'drawdown').sorted('id')[-1]

    @classmethod
    def _pay(cls, line, day=None, **vals):
        wizard = cls.env['account.loan.pay'].create({'line_id': line.id, **vals})
        if day:
            wizard.date = day
        wizard.action_confirm()
        return line.move_id

    @classmethod
    def _repay(cls, loan, day, amount, after='instalment', **vals):
        wizard = cls.env['account.loan.repay'].create({
            'loan_id': loan.id, 'date': day, 'amount': amount, 'after_repayment': after, **vals})
        wizard.action_confirm()
        return loan.operation_ids.filtered(lambda op: op.operation_type == 'repayment').sorted('id')[-1]

    def _lines(self, loan):
        return loan.line_ids.sorted('sequence')

    def _entry(self, move):
        """ The lines of `move` as {account code: (debit, credit, amount in currency)} """
        return {
            line.account_id.code: (line.debit, line.credit, line.amount_currency)
            for line in move.line_ids
        }
