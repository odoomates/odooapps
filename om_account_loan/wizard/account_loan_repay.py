import math

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.om_account_loan.models.account_loan import annuity_count


class AccountLoanRepay(models.TransientModel):
    _name = 'account.loan.repay'
    _description = 'Loan Early Repayment'
    _check_company_auto = True

    loan_id = fields.Many2one('account.loan', string='Loan', required=True)
    company_id = fields.Many2one(related='loan_id.company_id')
    currency_id = fields.Many2one(related='loan_id.currency_id')
    outstanding_amount = fields.Monetary(related='loan_id.outstanding_amount')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(
        string='Principal Repaid', required=True, compute='_compute_amount', store=True, readonly=False,
        precompute=True)
    interest = fields.Monetary(
        string='Interest Due', compute='_compute_interest', store=True, readonly=False, precompute=True,
        help="The interest accrued since the last due date, paid with the principal.")
    withholding_tax_id = fields.Many2one(related='loan_id.withholding_tax_id')
    withholding = fields.Monetary(
        string='Withholding Tax', compute='_compute_withholding', store=True, readonly=False, precompute=True,
        help="The tax withheld on the interest, deducted from the payment to the lender.")
    total = fields.Monetary(string='Total', compute='_compute_total')
    is_full = fields.Boolean(string='Full Repayment', compute='_compute_total')
    after_repayment = fields.Selection(
        [('term', 'Shorter Term'), ('instalment', 'Lower Instalment')], string='Then', required=True,
        default='instalment',
        help="Shorter Term: the instalments stay about the same, the loan ends earlier.\n"
             "Lower Instalment: the loan ends on the same date with lower instalments.")
    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal', required=True, check_company=True,
        compute='_compute_journal_id', store=True, readonly=False, precompute=True,
        domain="[('type', 'in', ('bank', 'cash'))]")

    @api.depends('loan_id')
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = wizard.loan_id.outstanding_amount

    @api.depends('loan_id', 'date')
    def _compute_interest(self):
        for wizard in self:
            loan = wizard.loan_id
            wizard.interest = loan._accrued_interest_at(wizard.date) if loan and wizard.date else 0.0

    @api.depends('loan_id', 'interest')
    def _compute_withholding(self):
        for wizard in self:
            wizard.withholding = wizard.loan_id._withholding_amount(wizard.interest) if wizard.loan_id else 0.0

    @api.depends('amount', 'interest', 'outstanding_amount')
    def _compute_total(self):
        for wizard in self:
            wizard.total = wizard.amount + wizard.interest
            wizard.is_full = not wizard.currency_id.compare_amounts(wizard.amount, wizard.outstanding_amount)

    @api.depends('loan_id')
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = wizard.loan_id.bank_journal_id

    def _check_repayment(self):
        loan = self.loan_id
        currency = loan.currency_id
        if loan.state != 'running':
            raise UserError(self.env._('The loan %s is not running.', loan.display_name))
        if loan.loan_type == 'lease':
            raise UserError(self.env._('A lease is not repaid early: its payments are billed by the lessor.'))
        if currency.compare_amounts(self.withholding, 0.0) < 0 or \
                currency.compare_amounts(self.withholding, max(self.interest, 0.0)) > 0:
            raise UserError(self.env._('The tax withheld must be between zero and the interest.'))
        if currency.compare_amounts(self.amount, 0.0) <= 0 or currency.compare_amounts(self.interest, 0.0) < 0:
            raise UserError(self.env._('The principal repaid must be positive, the interest too or zero.'))
        if currency.compare_amounts(self.amount, loan.outstanding_amount) > 0:
            raise UserError(self.env._(
                'The outstanding principal of the loan %(loan)s is %(amount)s.',
                loan=loan.display_name, amount=currency.format(loan.outstanding_amount)))
        loan._check_paid_up_to(self.date)
        due = loan.line_ids.filtered(lambda line: line.state == 'draft' and line.date <= self.date)
        if due:
            raise UserError(self.env._('Pay the instalments due on or before %s first.', self.date))
        if self.journal_id.currency_id and self.journal_id.currency_id != currency:
            raise UserError(self.env._('The bank journal is not in the currency of the loan.'))

    def _shorter_count(self, balance):
        """ The number of payments of the loan once `balance` is left, the next instalment (equal
        instalments) or principal (fixed principal) staying the same. """
        loan = self.loan_id
        paid = loan.line_ids.filtered(lambda line: line.state == 'posted')
        unpaid = loan.line_ids.filtered(lambda line: line.state == 'draft').sorted('sequence')
        following = unpaid[:1]
        if not following:
            return loan.payment_count
        if loan.schedule_method == 'annuity':
            rate = loan._rate_at(self.date) / 100 / loan._payments_per_year()
            count = annuity_count(balance, rate, following.amount)
        else:
            count = following.principal and math.ceil(balance / following.principal - 1e-9)
        return len(paid) + min(count or len(unpaid), len(unpaid))

    def action_confirm(self):
        """ Post Dr loan (principal) + Dr interest / Cr withholding tax + Cr bank, then compute the unpaid
        lines again: fewer of them for a shorter term, lower ones otherwise. A full repayment closes the
        loan. """
        self.ensure_one()
        self._check_repayment()
        loan = self.loan_id
        currency = loan.currency_id
        label = self.env._('%(loan)s - Early repayment', loan=loan.name)
        lines = loan._principal_lines(self.amount, self.date, label)
        lines.append((loan.account_interest_id, self.interest,
                      self.env._('%(loan)s - Interest to %(date)s', loan=loan.name, date=self.date),
                      loan._interest_line_values() if self.withholding else {}))
        lines += loan._withholding_lines(
            self.interest, self.withholding, self.date,
            self.env._('%(loan)s - Withholding tax to %(date)s', loan=loan.name, date=self.date))
        lines.append((loan._bank_account(self.journal_id, 'outbound'), 0.0, label))
        move = loan._create_move(self.journal_id, self.date, lines, 'repayment', label)
        balance = currency.round(loan.outstanding_amount - self.amount)
        count = loan.payment_count
        if not self.is_full and self.after_repayment == 'term':
            count = self._shorter_count(balance)
        self.env['account.loan.operation'].create({
            'loan_id': loan.id,
            'operation_type': 'repayment',
            'date': self.date,
            'amount': self.amount,
            'interest': self.interest,
            'withholding': self.withholding,
            'journal_id': self.journal_id.id,
            'move_id': move.id,
            'after_repayment': self.after_repayment,
            'payment_count_before': loan.payment_count,
        })
        if self.is_full:
            loan.line_ids.filtered(lambda line: line.state == 'draft').with_context(
                loan_schedule_update=True).unlink()
        else:
            if count != loan.payment_count:
                loan.with_context(loan_no_regenerate=True).payment_count = count
            loan._generate_schedule()
        loan._update_state()
        loan.message_post(body=self.env._(
            'Early repayment of %(amount)s on %(date)s.', amount=currency.format(self.amount), date=self.date))
        return {'type': 'ir.actions.act_window_close'}
