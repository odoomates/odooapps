from odoo import api, fields, models
from odoo.exceptions import UserError

LOAN_ENTRY_TYPES = [
    ('drawdown', 'Drawdown'),
    ('recognition', 'Lease Recognition'),
    ('payment', 'Instalment'),
    ('bill', 'Lease Bill'),
    ('repayment', 'Early Repayment'),
    ('reclassification', 'Reclassification'),
]
# the entries cancelled from the loan only, which follows them in its schedule
SCHEDULE_ENTRY_TYPES = ('drawdown', 'recognition', 'payment', 'bill', 'repayment')


class AccountMove(models.Model):
    _inherit = 'account.move'

    loan_id = fields.Many2one(
        'account.loan', string='Loan', readonly=True, copy=False, index='btree_not_null', check_company=True,
        groups='account.group_account_readonly,account.group_account_manager')
    loan_entry_type = fields.Selection(
        LOAN_ENTRY_TYPES, string='Loan Entry', readonly=True, copy=False,
        groups='account.group_account_readonly,account.group_account_manager')

    def _loan_schedule_entries(self):
        return self.sudo().filtered(lambda move: move.loan_entry_type in SCHEDULE_ENTRY_TYPES)

    def _check_draftable(self):
        super()._check_draftable()
        if self._loan_schedule_entries() and not self.env.context.get('loan_reverse'):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))

    def button_cancel(self):
        if self._loan_schedule_entries() and not self.env.context.get('loan_reverse'):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))
        return super().button_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_loan_schedule(self):
        if self._loan_schedule_entries() and not self.env.context.get('loan_reverse'):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if self._loan_schedule_entries() and not self.env.context.get('loan_reverse'):
            raise UserError(self.env._(
                'This entry belongs to the schedule of a loan: cancel it from the loan.'))
        default_values_list = default_values_list or [{} for _move in self]
        for move, values in zip(self.sudo(), default_values_list, strict=True):
            if move.loan_id:
                # the reversal stays in the balances of the loan
                values.setdefault('loan_id', move.loan_id.id)
                values.setdefault('loan_entry_type', move.loan_entry_type)
        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
