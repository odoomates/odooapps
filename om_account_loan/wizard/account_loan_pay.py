from odoo import api, fields, models


class AccountLoanPay(models.TransientModel):
    _name = 'account.loan.pay'
    _description = 'Pay a Loan Instalment'
    _check_company_auto = True

    line_id = fields.Many2one('account.loan.line', string='Instalment', required=True)
    loan_id = fields.Many2one(related='line_id.loan_id')
    company_id = fields.Many2one(related='line_id.company_id')
    currency_id = fields.Many2one(related='line_id.currency_id')
    date = fields.Date(
        string='Payment Date', required=True, compute='_compute_date', store=True, readonly=False, precompute=True)
    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal', required=True, check_company=True,
        compute='_compute_journal_id', store=True, readonly=False, precompute=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    principal = fields.Monetary(
        string='Principal', compute='_compute_principal', store=True, readonly=False, precompute=True)
    interest = fields.Monetary(
        string='Interest', compute='_compute_interest', store=True, readonly=False, precompute=True)
    amount = fields.Monetary(string='Total', compute='_compute_amount')

    @api.depends('line_id')
    def _compute_date(self):
        for wizard in self:
            wizard.date = wizard.line_id.date

    @api.depends('line_id')
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = wizard.line_id.loan_id.bank_journal_id

    @api.depends('line_id')
    def _compute_principal(self):
        for wizard in self:
            wizard.principal = wizard.line_id.principal

    @api.depends('line_id')
    def _compute_interest(self):
        for wizard in self:
            wizard.interest = wizard.line_id.interest

    @api.depends('principal', 'interest')
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = wizard.principal + wizard.interest

    def action_confirm(self):
        """ Post Dr loan (principal) + Dr interest / Cr bank (outstanding payments) for the instalment; a
        principal or an interest changed here is written on the instalment first. """
        self.ensure_one()
        line = self.line_id
        currency = line.currency_id
        changes = {fname: self[fname] for fname in ('principal', 'interest')
                   if currency.compare_amounts(self[fname], line[fname])}
        if changes:
            line.write(changes)
        line._post_payment(self.date, self.journal_id)
        return {'type': 'ir.actions.act_window_close'}
