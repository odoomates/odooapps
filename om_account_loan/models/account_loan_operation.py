from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountLoanOperation(models.Model):
    _name = 'account.loan.operation'
    _description = 'Loan Drawdown, Early Repayment or Lease Recognition'
    _order = 'loan_id, date, id'
    _check_company_auto = True

    loan_id = fields.Many2one('account.loan', string='Loan', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='loan_id.currency_id', store=True)
    operation_type = fields.Selection(
        [('drawdown', 'Drawdown'), ('recognition', 'Initial Recognition'), ('repayment', 'Early Repayment')],
        string='Type', required=True, readonly=True)
    date = fields.Date(string='Date', required=True, readonly=True)
    amount = fields.Monetary(string='Principal', readonly=True)
    interest = fields.Monetary(string='Interest', readonly=True, help="The interest paid with an early repayment.")
    withholding = fields.Monetary(
        string='Withholding Tax', readonly=True, help="The tax withheld on the interest of an early repayment.")
    total = fields.Monetary(string='Total', compute='_compute_total')
    journal_id = fields.Many2one('account.journal', string='Journal', readonly=True, check_company=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, check_company=True)
    after_repayment = fields.Selection(
        [('term', 'Shorter Term'), ('instalment', 'Lower Instalment')], string='Then', readonly=True)
    payment_count_before = fields.Integer(readonly=True, help="The number of payments before a shorter term.")
    state = fields.Selection(
        [('posted', 'Posted'), ('cancel', 'Cancelled')], string='Status', required=True, default='posted',
        readonly=True)

    @api.depends('amount', 'interest')
    def _compute_total(self):
        for operation in self:
            operation.total = operation.amount + operation.interest

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted(self):
        if self.filtered(lambda op: op.state == 'posted'):
            raise UserError(self.env._('Cancel the operation instead of deleting it.'))

    def action_cancel(self):
        """ Reverse the entry of the operation and compute the schedule again without it. """
        for operation in self.filtered(lambda op: op.state == 'posted'):
            loan = operation.loan_id
            paid = loan.line_ids.filtered(lambda line: line.state == 'posted' and line.date >= operation.date)
            if paid:
                raise UserError(self.env._(
                    'Cancel the payment of the instalments due after %s first.', operation.date))
            later = loan.operation_ids.filtered(
                lambda op: op.state == 'posted' and (op.date, op.id) > (operation.date, operation.id))
            if later:
                raise UserError(self.env._('Cancel the later operations of the loan first.'))
            if operation.operation_type in ('drawdown', 'recognition'):
                if loan.currency_id.compare_amounts(loan.outstanding_amount, operation.amount) < 0:
                    raise UserError(self.env._('Without the drawdown, the loan would repay more than it draws.'))
            if operation.move_id:
                operation.move_id.with_context(loan_reverse=True)._reverse_moves(
                    [{'date': operation.move_id.date}], cancel=True)
            operation.state = 'cancel'
            if operation.after_repayment == 'term' and operation.payment_count_before:
                loan.with_context(loan_no_regenerate=True).payment_count = operation.payment_count_before
            if loan.state == 'closed':
                loan.state = 'running'
            loan.message_post(body=self.env._(
                '%(operation)s of %(date)s cancelled.',
                operation=dict(self._fields['operation_type'].selection)[operation.operation_type],
                date=operation.date))
            loan._generate_schedule()
            loan._update_state()

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }
