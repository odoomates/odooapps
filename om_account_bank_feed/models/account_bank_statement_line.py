from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    bank_feed_transaction_id = fields.Char(
        string='Bank Feed Transaction', readonly=True, copy=False, index='btree_not_null',
        help="The identifier of the transaction at the bank feed provider: a transaction already imported in "
             "the journal is not imported again.")
    bank_feed_account_id = fields.Many2one(
        'bank.feed.account', string='Bank Feed Account', readonly=True, copy=False, index='btree_not_null',
        ondelete='set null')
    bank_feed_pending = fields.Boolean(
        string='Pending at the Bank', readonly=True, copy=False,
        help="The bank has not booked this transaction yet: it is replaced by the booked transaction, or "
             "removed when the bank drops it.")

    _bank_feed_transaction_uniq = models.Constraint(
        'UNIQUE(journal_id, bank_feed_transaction_id)',
        'A transaction of a bank feed is imported only once in a journal.',
    )
