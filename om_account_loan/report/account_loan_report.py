from odoo import api, fields, models
from odoo.fields import Command


class AccountLoanReport(models.TransientModel):
    _name = 'account.loan.report'
    _description = 'Loan Report'

    date = fields.Date(string='At', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    loan_ids = fields.Many2many(
        'account.loan', string='Loans', domain="[('company_id', '=', company_id), ('state', '!=', 'cancel')]",
        help="Leave empty for every loan of the company.")
    line_ids = fields.One2many('account.loan.report.line', 'report_id', string='Lines')

    def _get_loans(self):
        self.ensure_one()
        return self.loan_ids or self.env['account.loan'].search([
            ('company_id', '=', self.company_id.id), ('state', 'in', ('running', 'closed')),
            ('date_start', '<=', self.date)])

    def _compute_lines(self):
        self.ensure_one()
        self.line_ids = [Command.clear()] + [
            Command.create(self.env['account.loan.report.line']._values_at(loan, self.date))
            for loan in self._get_loans()
        ]

    def action_view(self):
        self._compute_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Loans at %s', self.date),
            'res_model': 'account.loan.report.line',
            'view_mode': 'list,pivot',
            'domain': [('report_id', '=', self.id)],
            'context': {'create': False, 'edit': False, 'delete': False},
        }

    def action_print(self):
        self._compute_lines()
        return self.env.ref('om_account_loan.action_report_loan_position').report_action(self)


class AccountLoanReportLine(models.TransientModel):
    _name = 'account.loan.report.line'
    _description = 'Loan Report Line'
    _order = 'report_id, date_start, loan_id'

    report_id = fields.Many2one('account.loan.report', required=True, ondelete='cascade', index=True)
    date = fields.Date(related='report_id.date', string='At')
    loan_id = fields.Many2one('account.loan', string='Loan', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Lender')
    company_id = fields.Many2one('res.company', string='Company')
    currency_id = fields.Many2one('res.currency', string='Currency')
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')
    date_start = fields.Date(string='Start Date')
    rate = fields.Float(string='Rate (%)', digits=(16, 4), aggregator=None)
    principal = fields.Monetary(string='Principal')
    outstanding = fields.Monetary(string='Outstanding Principal')
    accrued_interest = fields.Monetary(string='Accrued Interest')
    next_date = fields.Date(string='Next Due Date')
    next_amount = fields.Monetary(string='Next Instalment')
    due_within = fields.Monetary(string='Due within 12 Months')
    due_after = fields.Monetary(string='Due after 12 Months')
    outstanding_company = fields.Monetary(
        string='Outstanding (Company Currency)', currency_field='company_currency_id',
        help="The principal outstanding at its value in the books: the rates of the drawdowns and payments.")

    @api.model
    def _values_at(self, loan, day):
        """ The position of `loan` on `day`. """
        outstanding = loan._outstanding_at(day)
        within = loan._principal_due_within(day)
        following = loan._lines_unpaid_at(day)[:1]
        booked = sum(
            loan._account_balance_at(account, day, company_currency=True)
            for account in loan.account_long_term_id | loan.account_short_term_id)
        return {
            'loan_id': loan.id,
            'partner_id': loan.partner_id.id,
            'company_id': loan.company_id.id,
            'currency_id': loan.currency_id.id,
            'date_start': loan.date_start,
            'rate': loan._rate_at(day),
            'principal': loan.principal,
            'outstanding': outstanding,
            'accrued_interest': loan._accrued_interest_at(day) if outstanding else 0.0,
            'next_date': following.date,
            'next_amount': following.amount,
            'due_within': within,
            'due_after': loan.currency_id.round(outstanding - within),
            'outstanding_company': booked,
        }
