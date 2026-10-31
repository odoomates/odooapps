from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountLoanDrawdown(models.TransientModel):
    _name = 'account.loan.drawdown'
    _description = 'Loan Drawdown'
    _check_company_auto = True

    loan_id = fields.Many2one('account.loan', string='Loan', required=True)
    company_id = fields.Many2one(related='loan_id.company_id')
    currency_id = fields.Many2one(related='loan_id.currency_id')
    undrawn_amount = fields.Monetary(related='loan_id.undrawn_amount')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(
        string='Amount', compute='_compute_amount', store=True, readonly=False, precompute=True, required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal', required=True, check_company=True,
        compute='_compute_journal_id', store=True, readonly=False, precompute=True,
        domain="[('type', 'in', ('bank', 'cash'))]")

    @api.depends('loan_id')
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = wizard.loan_id.undrawn_amount

    @api.depends('loan_id')
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = wizard.loan_id.bank_journal_id

    def _check_drawdown(self):
        loan = self.loan_id
        currency = loan.currency_id
        if loan.state != 'running':
            raise UserError(self.env._('Confirm the loan %s first.', loan.display_name))
        if currency.compare_amounts(self.amount, 0.0) <= 0:
            raise UserError(self.env._('The amount of a drawdown must be positive.'))
        if currency.compare_amounts(self.amount, loan.undrawn_amount) > 0:
            raise UserError(self.env._(
                'The loan %(loan)s has %(amount)s left to draw.',
                loan=loan.display_name, amount=currency.format(loan.undrawn_amount)))
        if self.date < loan.date_start:
            raise UserError(self.env._('A drawdown cannot be dated before the start of the loan.'))
        last = loan.line_ids.sorted('sequence')[-1:]
        if last and self.date >= last.date:
            raise UserError(self.env._('A drawdown must be dated before the last instalment of the loan.'))
        if self.journal_id.currency_id and self.journal_id.currency_id != currency:
            raise UserError(self.env._('The bank journal is not in the currency of the loan.'))
        loan._check_paid_up_to(self.date)

    def action_confirm(self):
        """ Post Dr bank (outstanding receipts) / Cr long-term loan, then compute the unpaid lines again from
        the principal drawn. """
        self.ensure_one()
        self._check_drawdown()
        loan = self.loan_id
        label = self.env._('%(loan)s - Drawdown', loan=loan.name)
        move = loan._create_move(self.journal_id, self.date, [
            (loan.account_long_term_id, -self.amount, label),
            (loan._bank_account(self.journal_id, 'inbound'), 0.0, label),
        ], 'drawdown', label)
        self.env['account.loan.operation'].create({
            'loan_id': loan.id,
            'operation_type': 'drawdown',
            'date': self.date,
            'amount': self.amount,
            'journal_id': self.journal_id.id,
            'move_id': move.id,
        })
        loan._generate_schedule()
        loan.message_post(body=self.env._(
            'Drawdown of %(amount)s on %(date)s.', amount=loan.currency_id.format(self.amount), date=self.date))
        return {'type': 'ir.actions.act_window_close'}
