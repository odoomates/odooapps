from odoo import api, fields, models
from odoo.exceptions import UserError

from .loan_context import LOAN_REVERSE, LOAN_WRITE, internal, internal_context

LOAN_ENTRY_TYPES = [
    ('drawdown', 'Drawdown'),
    ('recognition', 'Lease Recognition'),
    ('payment', 'Instalment'),
    ('bill', 'Lease Bill'),
    ('repayment', 'Early Repayment'),
    ('reclassification', 'Reclassification'),
    ('exchange', 'Exchange Difference'),
]
# the entries cancelled from the loan only, which follows them in its schedule
SCHEDULE_ENTRY_TYPES = ('drawdown', 'recognition', 'payment', 'bill', 'repayment', 'exchange')
# the entries repaying principal in a foreign currency: the exchange difference on it is realized
REPAYING_ENTRY_TYPES = ('payment', 'bill', 'repayment', 'reclassification')


class AccountMove(models.Model):
    _inherit = 'account.move'

    loan_id = fields.Many2one(
        'account.loan', string='Loan', readonly=True, copy=False, index='btree_not_null', check_company=True,
        groups='account.group_account_readonly,account.group_account_manager')
    loan_entry_type = fields.Selection(
        LOAN_ENTRY_TYPES, string='Loan Entry', readonly=True, copy=False,
        groups='account.group_account_readonly,account.group_account_manager')
    loan_exchange_move_id = fields.Many2one(
        'account.move', string='Loan Exchange Difference', readonly=True, copy=False, index='btree_not_null',
        groups='account.group_account_readonly,account.group_account_manager',
        help="The exchange difference realized on the principal this entry repays, in a foreign currency loan.")

    loan_reclassified_amount = fields.Monetary(
        string='Moved to Short Term', compute='_compute_loan_reclassified_amount',
        groups='account.group_account_readonly,account.group_account_manager',
        help="The principal a reclassification moved to the short-term account; negative, back to the long-term "
             "account.")

    @api.depends('line_ids.amount_currency', 'loan_entry_type')
    def _compute_loan_reclassified_amount(self):
        for move in self:
            amount = 0.0
            if move.loan_entry_type == 'reclassification' and move.loan_id:
                short_term = move.loan_id.account_short_term_id
                amount = -sum(move.line_ids.filtered(lambda line: line.account_id == short_term).mapped(
                    'amount_currency'))
            move.loan_reclassified_amount = amount

    def _loan_schedule_entries(self):
        return self.sudo().filtered(lambda move: move.loan_entry_type in SCHEDULE_ENTRY_TYPES)

    def write(self, vals):
        if {'loan_id', 'loan_entry_type'} & set(vals) and not internal(self.env, LOAN_WRITE) \
                and self.sudo().filtered(lambda move: move.loan_id and move.state == 'posted'):
            raise UserError(self.env._('A posted entry of a loan stays linked to its loan.'))
        return super().write(vals)

    def _post(self, soft=True):
        # a lease bill left in draft is posted as its lease payment says
        for bill in self.sudo().filtered(lambda move: move.loan_entry_type == 'bill' and move.state == 'draft'):
            line = self.env['account.loan.line'].sudo().search([('move_id', '=', bill.id)], limit=1)
            if line:
                line._check_bill(bill)
        posted = super()._post(soft=soft)
        # the principal repaid in a foreign currency leaves the liability at its carrying rate
        for move in posted.sudo().filtered(lambda move: (
                move.loan_entry_type in REPAYING_ENTRY_TYPES and not move.reversed_entry_id
                and move.loan_id.currency_id != move.company_id.currency_id)):
            move.loan_id._settle_exchange(move)
        return posted

    def _loan_needs_document_number(self):
        """ Whether the bill needs a document number entered by hand before it is posted: the journals using
        documents (the localizations of Latin America) ask for the number of the lessor's document. """
        self.ensure_one()
        journal = self.journal_id
        return bool(journal._fields.get('l10n_latam_use_documents') and journal.l10n_latam_use_documents)

    def _check_draftable(self):
        super()._check_draftable()
        if self._loan_schedule_entries() and not internal(self.env, LOAN_REVERSE):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))

    def button_cancel(self):
        if self._loan_schedule_entries() and not internal(self.env, LOAN_REVERSE):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))
        return super().button_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_loan_schedule(self):
        if self._loan_schedule_entries() and not internal(self.env, LOAN_REVERSE):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if self._loan_schedule_entries() and not internal(self.env, LOAN_REVERSE):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))
        default_values_list = default_values_list or [{} for _move in self]
        # the exchange difference of an entry goes with it
        exchanges = self.sudo().loan_exchange_move_id.filtered(lambda move: move.state == 'posted')
        if exchanges:
            exchanges.with_context(**internal_context(LOAN_REVERSE))._reverse_moves(
                [{'date': move.date} for move in exchanges], cancel=True)
        reversals = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        # the reversal stays in the balances of the loan; written by the loan, as the user reversing an entry
        # (an invoicing user reversing a reclassification) may not see the loan fields
        for reversal in reversals.sudo():
            original = reversal.reversed_entry_id
            if original.loan_id:
                reversal.with_context(**internal_context(LOAN_WRITE)).write({
                    'loan_id': original.loan_id.id, 'loan_entry_type': original.loan_entry_type})
        return reversals
