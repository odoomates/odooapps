from odoo import api, fields, models
from odoo.exceptions import UserError

# fields set by the schedule, which a paid line keeps
SCHEDULE_FIELDS = {'date', 'opening_balance', 'principal', 'interest', 'rate', 'sequence'}


class AccountLoanLine(models.Model):
    _name = 'account.loan.line'
    _description = 'Loan Schedule Line'
    _order = 'loan_id, sequence, id'
    _check_company_auto = True

    loan_id = fields.Many2one('account.loan', string='Loan', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='loan_id.currency_id', store=True)
    partner_id = fields.Many2one(related='loan_id.partner_id', string='Lender')
    sequence = fields.Integer(string='#', required=True, default=1)
    date = fields.Date(string='Due Date', required=True)
    opening_balance = fields.Monetary(
        string='Opening Balance', help="The principal owed on the due date, before the instalment.")
    principal = fields.Monetary(string='Principal')
    interest = fields.Monetary(string='Interest')
    amount = fields.Monetary(string='Instalment', compute='_compute_amounts', store=True)
    closing_balance = fields.Monetary(string='Closing Balance', compute='_compute_amounts', store=True)
    rate = fields.Float(string='Rate (%)', digits=(16, 4), help="The annual rate of the period.")
    state = fields.Selection(
        [('draft', 'To Pay'), ('posted', 'Paid')], string='Status', required=True, default='draft', copy=False)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False, check_company=True)
    payment_date = fields.Date(string='Paid On', readonly=True, copy=False)
    loan_state = fields.Selection(related='loan_id.state', string='Loan Status')
    is_last_paid = fields.Boolean(compute='_compute_is_last_paid')

    @api.depends('principal', 'interest', 'opening_balance')
    def _compute_amounts(self):
        for line in self:
            line.amount = line.principal + line.interest
            line.closing_balance = line.opening_balance - line.principal

    @api.depends('state', 'loan_id.line_ids.state')
    def _compute_is_last_paid(self):
        for line in self:
            paid = line.loan_id.line_ids.filtered(lambda other: other.state == 'posted')
            line.is_last_paid = line.state == 'posted' and line == paid.sorted('sequence')[-1:]

    def write(self, vals):
        if not self.env.context.get('loan_schedule_update'):
            if SCHEDULE_FIELDS & set(vals) and self.filtered(lambda line: line.state == 'posted'):
                raise UserError(self.env._('A paid instalment cannot be changed.'))
            if {'state', 'move_id', 'payment_date'} & set(vals):
                raise UserError(self.env._('Pay an instalment with its Pay button.'))
        res = super().write(vals)
        if not self.env.context.get('loan_schedule_update') and {'principal', 'date'} & set(vals):
            self.loan_id._chain_balances()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_paid(self):
        if not self.env.context.get('loan_schedule_update') and self.filtered(lambda line: line.state == 'posted'):
            raise UserError(self.env._('A paid instalment cannot be deleted.'))

    def action_pay(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Pay Instalment'),
            'res_model': 'account.loan.pay',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    def _post_payment(self, day, journal):
        """ Post the payment of the instalment on `day` from `journal`: Dr loan (principal) + Dr interest / Cr
        bank (outstanding payments). An instalment of zero is marked paid without entry. """
        self.ensure_one()
        loan = self.loan_id
        if self.state == 'posted':
            raise UserError(self.env._('The instalment %s is already paid.', self.sequence))
        if loan.state != 'running':
            raise UserError(self.env._('The loan %s is not running.', loan.display_name))
        earlier = loan.line_ids.filtered(lambda line: line.state == 'draft' and line.sequence < self.sequence)
        if earlier:
            raise UserError(self.env._('Pay the instalments in their order: %s first.', earlier[0].sequence))
        currency = self.currency_id
        if currency.compare_amounts(self.principal, loan.outstanding_amount) > 0:
            raise UserError(self.env._(
                'The principal of the instalment exceeds the outstanding principal of the loan %s.',
                loan.display_name))
        move = self.env['account.move']
        if not currency.is_zero(self.amount):
            label = self.env._('%(loan)s - Instalment %(number)s', loan=loan.name, number=self.sequence)
            lines = loan._principal_lines(self.principal, day, label)
            lines.append((loan.account_interest_id, self.interest,
                          self.env._('%(loan)s - Interest %(number)s', loan=loan.name, number=self.sequence)))
            lines.append((loan._bank_account(journal, 'outbound'), 0.0, label))
            move = loan._create_move(journal, day, lines, 'payment', label)
        self.with_context(loan_schedule_update=True).write({
            'state': 'posted', 'move_id': move.id, 'payment_date': day})
        loan._update_state()
        return move

    def action_cancel_payment(self):
        """ Reverse the payment of the last paid instalment: the line is to pay again. """
        for line in self:
            if not line.is_last_paid:
                raise UserError(self.env._('Only the last paid instalment can be cancelled.'))
            loan = line.loan_id
            later = loan.operation_ids.filtered(lambda op: op.state == 'posted' and op.date > line.date)
            if later:
                raise UserError(self.env._('Cancel the operations dated after the instalment first.'))
            if line.move_id:
                line.move_id.with_context(loan_reverse=True)._reverse_moves([{'date': line.move_id.date}], cancel=True)
            line.with_context(loan_schedule_update=True).write(
                {'state': 'draft', 'move_id': False, 'payment_date': False})
            loan.message_post(body=self.env._('Payment of the instalment %s cancelled.', line.sequence))
            if loan.state == 'closed':
                loan.state = 'running'
