from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_reconcile_auto = fields.Boolean(
        string='Reconcile New Transactions Automatically', default=True,
        help='When bank or cash transactions are created or imported, apply the automatic reconciliation models '
             'and reconcile the transactions matching exactly one open item by amount and reference.')
    om_reconcile_find_partner = fields.Boolean(
        string='Find the Partner of New Transactions', default=True,
        help='Set the partner of a new transaction when it is certain: the one partner owning the bank account of '
             'the other party, the one company with exactly the name written by the bank, or the one partner of '
             'the open invoice or bill whose number is the reference of the transaction. When several partners '
             'fit, the partner is left empty.')
    om_reconcile_tolerance = fields.Monetary(
        string='Payment Tolerance', currency_field='currency_id',
        help='A transaction differing from an open item by at most this amount still matches it; when the '
             'transaction is reconciled automatically, the difference goes to the payment difference account.')
    om_reconcile_fx_tolerance = fields.Float(
        string='Foreign Currency Tolerance (%)',
        help='An item in another currency than the transaction still matches it when the converted amounts differ '
             'by at most this percentage, as the rate of the bank differs from the rate of the day.')
    om_reconcile_tolerance_account_id = fields.Many2one(
        'account.account', string='Payment Difference Account', check_company=True,
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'off_balance'))]",
        help='Where the difference within the tolerance goes when a transaction is reconciled automatically.')
    om_bank_fee_account_id = fields.Many2one(
        'account.account', string='Bank Fees Account', check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost'))]",
        help='A reconciliation model "Bank Fees" is offered on every bank journal, booking the transaction on '
             'this account.')
