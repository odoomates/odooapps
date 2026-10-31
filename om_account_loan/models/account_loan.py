import calendar
import logging
import math
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain

PAYMENT_FREQUENCIES = [
    ('monthly', 'Monthly'),
    ('quarterly', 'Quarterly'),
    ('semiannual', 'Semi-annual'),
    ('annual', 'Annual'),
]
PAYMENTS_PER_YEAR = {'monthly': 12, 'quarterly': 4, 'semiannual': 2, 'annual': 1}
LOAN_TYPES = [('loan', 'Loan'), ('lease', 'Lease')]
ONE_DAY = timedelta(days=1)

_logger = logging.getLogger(__name__)


def annuity(balance, period_rate, count):
    """ The equal instalment repaying `balance` with its interest in `count` periods at `period_rate`. """
    if count <= 0:
        return balance
    if not period_rate:
        return balance / count
    return balance * period_rate / (1 - (1 + period_rate) ** -count)


def annuity_count(balance, period_rate, instalment):
    """ The number of instalments of `instalment` repaying `balance` at `period_rate`, None if they never do. """
    if instalment <= 0:
        return None
    if not period_rate:
        return math.ceil(balance / instalment - 1e-9)
    if instalment <= balance * period_rate:
        return None
    return math.ceil(-math.log(1 - balance * period_rate / instalment) / math.log(1 + period_rate) - 1e-9)


def add_months(day, months, end_of_month=False):
    """ `day` moved by `months` calendar months, on the last day of the month when `end_of_month`. """
    result = day + relativedelta(months=months)
    return result + relativedelta(day=31) if end_of_month else result


class AccountLoan(models.Model):
    _name = 'account.loan'
    _description = 'Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='/', tracking=True)
    loan_type = fields.Selection(
        LOAN_TYPES, string='Type', required=True, tracking=True,
        # not a default_ key of the context, which the lines of the schedule would take too
        default=lambda self: self.env.context.get('loan_default_type') or 'loan',
        help="Loan: money received from a lender, drawn down and repaid from the bank.\n"
             "Lease: an asset used under a lease, recognized as a lease liability at the present value of the "
             "lease payments; each payment is a vendor bill of the lessor.")
    partner_id = fields.Many2one(
        'res.partner', string='Lender', required=True, tracking=True, check_company=True,
        help="The bank or the person lending the money, or the lessor of a lease.")
    lender_ref = fields.Char(string='Lender Reference', tracking=True, help="The number of the contract at the lender.")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True, tracking=True,
        default=lambda self: self.env.company.currency_id)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency')
    principal = fields.Monetary(
        string='Principal', required=True, tracking=True,
        compute='_compute_principal', store=True, readonly=False, precompute=True,
        help="The amount of the loan: it is drawn in one or more drawdowns. For a lease, the lease liability: the "
             "present value of the lease payments at the rate of the lease.")
    lease_payment = fields.Monetary(
        string='Lease Payment', tracking=True,
        help="The amount of each payment of the lease, taxes excluded. The schedule splits it into the interest "
             "(the finance charge) and the reduction of the lease liability.")
    date_start = fields.Date(
        string='Start Date', required=True, default=fields.Date.context_today, tracking=True,
        help="The date of the contract. Until the first drawdown, the schedule assumes the principal is drawn on it.")
    payment_frequency = fields.Selection(
        PAYMENT_FREQUENCIES, string='Payment Frequency', required=True, default='monthly', tracking=True)
    date_first_payment = fields.Date(
        string='First Payment Date', required=True, tracking=True,
        compute='_compute_date_first_payment', store=True, readonly=False, precompute=True,
        help="The due date of the first instalment; the next ones fall on the same day of the month, or on the "
             "last day of the month when the first one does.")
    payment_count = fields.Integer(
        string='Number of Payments', required=True, default=12, tracking=True,
        help="The number of instalments of the loan. Repaying early with a shorter term reduces it.")
    rate_type = fields.Selection(
        [('fixed', 'Fixed'), ('floating', 'Floating')], string='Rate Type', required=True, default='fixed',
        tracking=True)
    rate = fields.Float(
        string='Annual Rate (%)', digits=(16, 4), tracking=True,
        help="The annual interest rate; a floating rate changes on the dates of its rate changes.")
    rate_line_ids = fields.One2many('account.loan.rate', 'loan_id', string='Rate Changes', copy=True)
    current_rate = fields.Float(
        string='Current Rate (%)', digits=(16, 4), compute='_compute_current_rate',
        help="The annual rate in force today.")
    schedule_method = fields.Selection(
        [('annuity', 'Equal Instalments (Annuity)'), ('fixed_principal', 'Fixed Principal'),
         ('imported', 'Imported')],
        string='Schedule Method', required=True, default='annuity', tracking=True,
        help="Equal instalments: the same amount every period, interest first.\n"
             "Fixed principal: the same principal every period, with the interest on the balance.\n"
             "Imported: the schedule given by the lender, imported from a file.")
    interest_method = fields.Selection(
        [('period', 'Rate / Payments per Year'), ('actual_365', 'Actual Days / 365')],
        string='Interest Method', required=True, default='period', tracking=True,
        help="Rate / Payments per Year: the interest of a whole period is the balance x the annual rate / the "
             "number of payments per year; a shorter period is counted in days.\n"
             "Actual Days / 365: the interest is the balance x the annual rate x the days of the period / 365.")
    account_long_term_id = fields.Many2one(
        'account.account', string='Long-term Loan Account', check_company=True, tracking=True,
        compute='_compute_accounts', store=True, readonly=False, precompute=True,
        help="The liability credited by the drawdowns (the initial recognition of a lease): the principal due in "
             "more than 12 months.")
    account_short_term_id = fields.Many2one(
        'account.account', string='Short-term Loan Account', check_company=True, tracking=True,
        compute='_compute_accounts', store=True, readonly=False, precompute=True,
        help="The liability for the principal due within 12 months, filled by the reclassification.")
    account_interest_id = fields.Many2one(
        'account.account', string='Interest Expense Account', check_company=True, tracking=True,
        default=lambda self: self.env.company.loan_interest_account_id)
    account_rou_id = fields.Many2one(
        'account.account', string='Right-of-use Asset Account', check_company=True, tracking=True,
        default=lambda self: self.env.company.lease_rou_account_id,
        help="The account debited by the initial recognition of a lease, against the lease liability.")
    journal_id = fields.Many2one(
        'account.journal', string='Loan Journal', check_company=True, tracking=True,
        domain="[('type', '=', 'general')]",
        default=lambda self: self.env.company.loan_journal_id,
        help="The journal of the reclassifications.")
    bank_journal_id = fields.Many2one(
        'account.journal', string='Bank Journal', check_company=True, tracking=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        default=lambda self: self.env.company.loan_bank_journal_id,
        help="The journal of the drawdowns and of the payments, unless another one is chosen when posting them.")
    bank_posting = fields.Selection(
        [('outstanding', 'Outstanding Receipts / Payments'), ('bank', 'Bank Account')],
        string='Post Bank Leg On', required=True, default='outstanding', tracking=True,
        help="Outstanding Receipts / Payments: the bank leg of the entries goes to the outstanding account of the "
             "bank journal, and is matched with the bank statement line when it comes in.\n"
             "Bank Account: the bank leg goes straight to the bank account of the journal, without statement "
             "reconciliation.")
    bill_journal_id = fields.Many2one(
        'account.journal', string='Bill Journal', check_company=True, tracking=True,
        domain="[('type', '=', 'purchase')]",
        default=lambda self: self.env.company.lease_bill_journal_id,
        help="The purchase journal of the bills of the lessor.")
    bill_posting = fields.Selection(
        [('posted', 'Posted'), ('draft', 'Draft')], string='Lease Bills', required=True, default='posted',
        tracking=True, help="Posted: the bills of the lease payments are posted when created.\n"
                            "Draft: they are left in draft, to check and post.")
    bill_auto_create = fields.Boolean(
        string='Bill on the Due Dates', default=True, tracking=True,
        help="Create the bill of each lease payment on its due date, by a daily scheduled action.")
    bill_tax_ids = fields.Many2many(
        'account.tax', 'account_loan_bill_tax_rel', 'loan_id', 'tax_id', string='Taxes on the Bills',
        check_company=True, domain="[('type_tax_use', '=', 'purchase')]",
        help="The taxes of the lease payments, such as the VAT, on the lines of the bills.")
    withholding_tax_id = fields.Many2one(
        'account.tax', string='Withholding Tax', check_company=True, tracking=True,
        domain="[('type_tax_use', 'in', ('purchase', 'none')), ('amount', '<', 0)]",
        help="The tax withheld on the interest, such as 1% in Thailand (P.N.D. 53): it is deducted from what is "
             "paid to the lender and booked on the account of the tax. A tax with a negative amount.")
    state = fields.Selection(
        [('draft', 'Draft'), ('running', 'Running'), ('closed', 'Closed'), ('cancel', 'Cancelled')],
        string='Status', required=True, default='draft', readonly=True, copy=False, tracking=True)
    line_ids = fields.One2many('account.loan.line', 'loan_id', string='Schedule', copy=False)
    operation_ids = fields.One2many('account.loan.operation', 'loan_id', string='Operations', copy=False)
    move_ids = fields.One2many('account.move', 'loan_id', string='Journal Entries', readonly=True, copy=False)
    move_count = fields.Integer(compute='_compute_move_count', string='Entry Count')
    drawn_amount = fields.Monetary(string='Drawn', compute='_compute_amounts', store=True)
    undrawn_amount = fields.Monetary(string='Undrawn', compute='_compute_amounts', store=True)
    outstanding_amount = fields.Monetary(
        string='Outstanding Principal', compute='_compute_amounts', store=True,
        help="The principal drawn and not repaid yet.")
    interest_total = fields.Monetary(string='Total Interest', compute='_compute_totals')
    next_line_id = fields.Many2one('account.loan.line', string='Next Instalment', compute='_compute_totals')
    next_date = fields.Date(string='Next Due Date', compute='_compute_totals')
    next_amount = fields.Monetary(string='Next Instalment Amount', compute='_compute_totals')
    date_end = fields.Date(string='Maturity', compute='_compute_totals')
    lease_end = fields.Date(
        string='End of Lease Term', compute='_compute_lease_end',
        help="The end of the last period of the lease: its last due date, or one period after it when the lease "
             "is paid in advance.")
    withholding_total = fields.Monetary(string='Total Withholding Tax', compute='_compute_totals')
    note = fields.Html(string='Notes')

    _positive_principal = models.Constraint('CHECK(principal > 0)', 'The principal of a loan must be positive.')
    _positive_count = models.Constraint('CHECK(payment_count > 0)', 'A loan has at least one payment.')
    _positive_rate = models.Constraint('CHECK(rate >= 0)', 'The interest rate cannot be negative.')

    # ------------------------------------------------------------
    # Computes and constraints
    # ------------------------------------------------------------

    @api.depends('date_start', 'payment_frequency')
    def _compute_date_first_payment(self):
        for loan in self:
            if loan.date_start and loan.payment_frequency:
                loan.date_first_payment = add_months(loan.date_start, loan._months_per_period())
            else:
                loan.date_first_payment = loan.date_first_payment or False

    @api.depends('loan_type', 'lease_payment', 'rate', 'payment_count', 'payment_frequency', 'date_start',
                 'date_first_payment', 'interest_method')
    def _compute_principal(self):
        for loan in self:
            if loan.loan_type == 'lease' and loan.state == 'draft':
                loan.principal = loan._lease_present_value()
            else:
                loan.principal = loan.principal

    @api.depends('loan_type', 'company_id')
    def _compute_accounts(self):
        for loan in self:
            company = loan.company_id or self.env.company
            if loan.loan_type == 'lease':
                loan.account_long_term_id = company.lease_long_term_account_id or company.loan_long_term_account_id
                loan.account_short_term_id = company.lease_short_term_account_id or company.loan_short_term_account_id
            else:
                loan.account_long_term_id = company.loan_long_term_account_id
                loan.account_short_term_id = company.loan_short_term_account_id

    @api.depends('loan_type', 'date_start', 'date_first_payment', 'payment_frequency', 'payment_count',
                 'line_ids.date')
    def _compute_lease_end(self):
        for loan in self:
            loan.lease_end = loan.loan_type == 'lease' and loan._lease_term_end()

    @api.depends('rate', 'rate_type', 'rate_line_ids.date', 'rate_line_ids.rate')
    @api.depends_context('date')
    def _compute_current_rate(self):
        today = fields.Date.context_today(self)
        for loan in self:
            loan.current_rate = loan._rate_at(today)

    @api.depends('move_ids')
    def _compute_move_count(self):
        for loan in self:
            loan.move_count = len(loan.move_ids)

    @api.depends('principal', 'operation_ids.state', 'operation_ids.amount', 'operation_ids.operation_type',
                 'line_ids.state', 'line_ids.principal')
    def _compute_amounts(self):
        for loan in self:
            operations = loan.operation_ids.filtered(lambda op: op.state == 'posted')
            drawn = sum(operations.filtered(lambda op: op.operation_type != 'repayment').mapped('amount'))
            repaid = sum(operations.filtered(lambda op: op.operation_type == 'repayment').mapped('amount'))
            repaid += sum(loan.line_ids.filtered(lambda line: line.state == 'posted').mapped('principal'))
            loan.drawn_amount = drawn
            loan.undrawn_amount = loan.principal - drawn
            loan.outstanding_amount = drawn - repaid

    @api.depends('line_ids.state', 'line_ids.interest', 'line_ids.date', 'line_ids.amount', 'line_ids.withholding')
    def _compute_totals(self):
        for loan in self:
            lines = loan.line_ids.sorted('sequence')
            following = lines.filtered(lambda line: line.state == 'draft')[:1]
            loan.interest_total = sum(lines.mapped('interest'))
            loan.withholding_total = sum(lines.mapped('withholding'))
            loan.next_line_id = following
            loan.next_date = following.date
            loan.next_amount = following.amount
            loan.date_end = lines[-1:].date

    @api.constrains('date_start', 'date_first_payment', 'loan_type')
    def _check_dates(self):
        for loan in self:
            if loan.loan_type == 'lease':
                if loan.date_first_payment < loan.date_start:
                    raise ValidationError(self.env._(
                        'The first payment of the lease %s cannot be due before its start date.', loan.display_name))
            elif loan.date_first_payment <= loan.date_start:
                raise ValidationError(self.env._(
                    'The first payment of the loan %s must be due after its start date.', loan.display_name))

    @api.constrains('loan_type', 'rate_type', 'schedule_method', 'lease_payment')
    def _check_lease_terms(self):
        for loan in self.filtered(lambda loan: loan.loan_type == 'lease'):
            if loan.rate_type != 'fixed' or loan.schedule_method != 'annuity':
                raise ValidationError(self.env._(
                    'The lease %s has a fixed rate and equal payments.', loan.display_name))
            if loan.currency_id.compare_amounts(loan.lease_payment, 0.0) < 0:
                raise ValidationError(self.env._('The payment of the lease %s cannot be negative.', loan.display_name))

    @api.constrains('withholding_tax_id')
    def _check_withholding_tax(self):
        for loan in self:
            tax = loan.withholding_tax_id
            if tax and (tax.amount_type not in ('percent', 'fixed') or tax.amount >= 0):
                raise ValidationError(self.env._(
                    'The withholding tax %(tax)s of %(loan)s must be a percentage or a fixed amount, negative: it '
                    'reduces what is paid to the lender.', tax=tax.display_name, loan=loan.display_name))

    @api.constrains('account_long_term_id', 'account_short_term_id', 'account_interest_id')
    def _check_accounts(self):
        for loan in self:
            if loan.account_long_term_id and loan.account_long_term_id == loan.account_short_term_id:
                raise ValidationError(self.env._(
                    'The long-term and short-term accounts of the loan %s must differ.', loan.display_name))
            for account in loan.account_long_term_id | loan.account_short_term_id:
                if account.account_type in ('asset_receivable', 'liability_payable'):
                    raise ValidationError(self.env._(
                        'The account %(account)s is a receivable or payable account: the loan %(loan)s needs '
                        'a liability account of its own.', account=account.display_name, loan=loan.display_name))

    @api.constrains('currency_id', 'bank_journal_id')
    def _check_bank_journal_currency(self):
        for loan in self:
            journal = loan.bank_journal_id
            if journal.currency_id and journal.currency_id != loan.currency_id:
                raise ValidationError(self.env._(
                    'The bank journal %(journal)s is in %(journal_currency)s: the loan %(loan)s is in %(currency)s.',
                    journal=journal.display_name, journal_currency=journal.currency_id.name,
                    loan=loan.display_name, currency=loan.currency_id.name))

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                day = vals.get('date_start') or fields.Date.context_today(self)
                code = 'account.loan.lease' if vals.get('loan_type') == 'lease' else 'account.loan'
                vals['name'] = self.env['ir.sequence'].with_company(company).with_context(
                    ir_sequence_date=day).next_by_code(code) or '/'
        return super().create(vals_list)

    def write(self, vals):
        locked = {'principal', 'currency_id', 'company_id', 'date_start', 'payment_frequency', 'date_first_payment',
                  'schedule_method', 'interest_method', 'loan_type', 'lease_payment'} & set(vals)
        if locked and any(loan._has_entries() for loan in self):
            raise UserError(self.env._(
                'The terms of a loan with journal entries cannot change: use an early repayment or a rate change.'))
        if {'rate', 'rate_type', 'payment_count'} & set(vals) and not self.env.context.get('loan_no_regenerate') \
                and any(loan.loan_type == 'lease' and loan._has_entries() for loan in self):
            raise UserError(self.env._(
                'The terms of a lease with journal entries cannot change: its liability is recognized at their '
                'present value.'))
        res = super().write(vals)
        if {'rate', 'rate_type', 'payment_count'} & set(vals) and not self.env.context.get('loan_no_regenerate'):
            self.filtered(lambda loan: loan.state == 'running')._generate_schedule()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_entries(self):
        for loan in self:
            if loan.state not in ('draft', 'cancel') or loan._has_entries():
                raise UserError(self.env._('Only draft or cancelled loans without entries can be deleted.'))

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    @api.onchange('loan_type')
    def _onchange_loan_type(self):
        if self.loan_type == 'lease':
            self.rate_type = 'fixed'
            self.schedule_method = 'annuity'

    def action_confirm(self):
        """ Run the loan and compute its schedule; a lease is recognized on its start date. """
        for loan in self:
            if loan.state != 'draft':
                raise UserError(self.env._('Only a draft loan can be confirmed.'))
            loan._check_configuration()
            loan.state = 'running'
            if loan.loan_type == 'lease':
                loan._recognize_lease()
            loan._generate_schedule()

    def action_recognize(self):
        """ Recognize again a lease whose initial recognition was cancelled. """
        for loan in self:
            if loan.loan_type != 'lease' or loan.state != 'running' or loan._recognition():
                raise UserError(self.env._('The lease %s is recognized already.', loan.display_name))
            loan._recognize_lease()
            loan._generate_schedule()

    def action_compute_schedule(self):
        for loan in self:
            if loan.state not in ('draft', 'running'):
                raise UserError(self.env._('The schedule of a closed or cancelled loan cannot be computed.'))
            loan._generate_schedule()

    def action_cancel(self):
        for loan in self:
            if loan._has_entries():
                raise UserError(self.env._(
                    'The loan %s has journal entries: cancel them on the loan first.', loan.display_name))
        self.write({'state': 'cancel'})

    def action_draft(self):
        for loan in self:
            if loan.state != 'cancel':
                raise UserError(self.env._('Only a cancelled loan can be reset to draft.'))
        self.line_ids.unlink()
        self.write({'state': 'draft'})

    def action_drawdown(self):
        return self._open_wizard('account.loan.drawdown', self.env._('Drawdown'))

    def action_import_schedule(self):
        self.ensure_one()
        if self.state not in ('draft', 'running') or self.schedule_method != 'imported':
            raise UserError(self.env._('Choose the Imported schedule method on a draft or running loan first.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Import Schedule'),
            'res_model': 'account.loan.import',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_loan_id': self.id},
        }

    def action_repay(self):
        return self._open_wizard('account.loan.repay', self.env._('Early Repayment'))

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('loan_id', '=', self.id)],
            'context': {'create': False, 'default_loan_id': self.id},
        }

    def _open_wizard(self, model, name):
        self.ensure_one()
        if self.state != 'running':
            raise UserError(self.env._('The loan %s is not running.', self.display_name))
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_loan_id': self.id},
        }

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _has_entries(self):
        self.ensure_one()
        return bool(self.move_ids.filtered(lambda move: move.state == 'posted'))

    def _check_configuration(self):
        self.ensure_one()
        required = ['account_long_term_id', 'account_short_term_id', 'account_interest_id', 'journal_id']
        required += ['bill_journal_id', 'lease_payment'] if self.loan_type == 'lease' else ['bank_journal_id']
        missing = [self._fields[fname].string for fname in required if not self[fname]]
        if self.loan_type == 'lease' and not self._rou_account():
            missing.append(self._fields['account_rou_id'].string)
        if missing:
            raise UserError(self.env._(
                'Set these fields on the loan %(loan)s first: %(fields)s.',
                loan=self.display_name, fields=', '.join(missing)))
        if self.schedule_method == 'imported' and not self.line_ids:
            raise UserError(self.env._('Import the schedule of the loan %s first.', self.display_name))

    def _payments_per_year(self):
        return PAYMENTS_PER_YEAR[self.payment_frequency]

    def _months_per_period(self):
        return 12 // self._payments_per_year()

    def _due_date(self, index):
        """ The due date of the instalment `index` (0 for the first one), in calendar months from the first
        payment: 31 January gives 28 or 29 February, then 31 March. """
        first = self.date_first_payment
        end_of_month = first.day == calendar.monthrange(first.year, first.month)[1]
        return add_months(first, index * self._months_per_period(), end_of_month)

    def _rate_at(self, day):
        """ The annual rate (%) in force on `day`. """
        self.ensure_one()
        rate = self.rate
        if self.rate_type == 'floating':
            for change in self.rate_line_ids.sorted('date'):
                if change.date <= day:
                    rate = change.rate
        return rate

    def _principal_events(self, projection=True):
        """ The changes of the principal other than the instalments, by date: the drawdowns and the initial
        recognition of a lease (positive) and the early repayments (negative, they settle the interest due on
        their date).

        :param projection: before the first drawdown, the principal is assumed drawn on the start date; an
            imported schedule assumes the principal not drawn yet is drawn on the start date
        :return: list of (date, amount, settles the interest)
        """
        self.ensure_one()
        operations = self.operation_ids.filtered(lambda op: op.state == 'posted').sorted(lambda op: (op.date, op.id))
        events = [
            (op.date, -op.amount if op.operation_type == 'repayment' else op.amount, op.operation_type == 'repayment')
            for op in operations
        ]
        if projection:
            draws = operations.filtered(lambda op: op.operation_type != 'repayment')
            if not draws:
                events.insert(0, (self.date_start, self.principal, False))
            elif self.schedule_method == 'imported':
                undrawn = self.currency_id.round(self.principal - sum(draws.mapped('amount')))
                if self.currency_id.compare_amounts(undrawn, 0.0) > 0:
                    events.insert(0, (self.date_start, undrawn, False))
        return events

    def _period_factor(self, start, end, index, rate):
        """ The interest of one unit of balance from the end of `start` to the end of `end` in the period of
        the instalment `index`, at the annual `rate` (%), as `_interest_for` counts it. """
        days = max((end - start).days, 0)
        if self.interest_method == 'actual_365':
            return rate / 100 * days / 365
        return rate / 100 / self._payments_per_year() * days / self._period_days(index)

    def _lease_present_value(self):
        """ The present value of the lease payments at the rate of the lease, discounted as the schedule
        counts the interest: the schedule then repays it with the lease payments exactly, but for the rounding.
        A payment due on the start date (a lease paid in advance) is not discounted. """
        self.ensure_one()
        if not (self.lease_payment and self.payment_count > 0 and self.date_start and self.date_first_payment
                and self.payment_frequency):
            return 0.0
        balance = 0.0
        for index in reversed(range(self.payment_count)):
            start = self._due_date(index - 1) if index else self.date_start
            balance = (balance + self.lease_payment) / (
                1 + self._period_factor(start, self._due_date(index), index, self.rate))
        return self.currency_id.round(balance)

    def _lease_term_end(self):
        """ The end of the lease term: its last due date, or one period after it when paid in advance. """
        self.ensure_one()
        if not (self.date_first_payment and self.date_start and self.payment_frequency and self.payment_count > 0):
            return False
        last = self.line_ids.sorted('sequence')[-1:].date or self._due_date(self.payment_count - 1)
        if self.date_first_payment == self.date_start:
            return add_months(last, self._months_per_period())
        return last

    def _period_days(self, index):
        """ The days of the whole period of the instalment `index`. """
        return (self._due_date(index) - self._due_date(index - 1)).days

    def _interest_for(self, start, end, balance, events, period_rate, period_days):
        """ The interest from the end of `start` to the end of `end`, not rounded, on `balance` changed by
        `events` dated in (start, end]. A drawdown accrues from the day after it, an early repayment settles
        the interest due up to its date. A floating rate changes during the period with the actual days method;
        the other method takes `period_rate`, the rate at the start of the period.

        :return: (interest, balance at the end)
        """
        cuts = {day for day, _amount, _settles in events}
        if self.interest_method == 'actual_365' and self.rate_type == 'floating':
            # a rate changing on a day applies from that day: the segment before it ends the day before
            cuts |= {change.date - ONE_DAY for change in self.rate_line_ids if start < change.date - ONE_DAY < end}
        interest = 0.0
        day = start
        for cut in [*sorted(cut for cut in cuts if start < cut < end), end]:
            if cut > day:
                days = (cut - day).days
                if self.interest_method == 'actual_365':
                    interest += balance * self._rate_at(day + ONE_DAY) / 100 * days / 365
                else:
                    interest += balance * period_rate / 100 / self._payments_per_year() * days / period_days
                day = cut
            for event_day, amount, settles in events:
                if event_day == cut:
                    balance += amount
                    if settles:
                        interest = 0.0
        return interest, balance

    # ------------------------------------------------------------
    # The schedule
    # ------------------------------------------------------------

    def _kept_lines(self, date_from=None):
        """ The lines kept by a regeneration: the paid ones, and the unpaid ones due before `date_from`. """
        kept = self.env['account.loan.line']
        for line in self.line_ids.sorted('sequence'):
            if line.state != 'posted' and (not date_from or line.date >= date_from):
                break
            kept |= line
        return kept

    def _schedule_start(self, kept, events):
        """ :return: (the date the interest of the next line runs from, the balance on that date) """
        if kept:
            start = kept[-1].date
        elif events:
            start = min(day for day, _amount, _settles in events)
        else:
            raise UserError(self.env._('Nothing is drawn on the loan %s.', self.display_name))
        balance = sum(amount for day, amount, _settles in events if day <= start) - sum(kept.mapped('principal'))
        return start, self.currency_id.round(balance)

    def _compute_schedule_values(self, kept):
        """ The values of the lines following `kept`, from the principal drawn and repaid: a new instalment
        (or principal per period) is computed from the balance when it changes other than by the instalments,
        or when the rate changes. The last line repays what is left, rounding included.

        :return: list of dicts with date, opening_balance, principal, interest, rate
        """
        self.ensure_one()
        if self.schedule_method == 'imported':
            return self._imported_schedule_values(kept)
        count = self.payment_count - len(kept)
        if count <= 0:
            return []
        currency = self.currency_id
        events = self._principal_events()
        previous, balance = self._schedule_start(kept, events)
        events = [event for event in events if event[0] > previous]
        payments_per_year = self._payments_per_year()
        instalment = principal_per_period = rate_used = None
        values = []
        for step in range(count):
            index = len(kept) + step
            due = self._due_date(index)
            period_events = [event for event in events if previous < event[0] <= due]
            rate = self._rate_at(previous + ONE_DAY)
            interest = 0.0
            if due > previous:
                interest, balance = self._interest_for(
                    previous, due, balance, period_events, rate, self._period_days(index))
            balance = currency.round(balance)
            interest = currency.round(interest)
            left = count - step
            if period_events or instalment is None:
                principal_per_period = balance / left
            if period_events or instalment is None or rate != rate_used:
                instalment = annuity(balance, rate / 100 / payments_per_year, left)
                rate_used = rate
            if self.loan_type == 'lease':
                # the payments of the contract, the liability being their present value
                instalment = self.lease_payment
            if left == 1:
                principal = balance
            elif self.schedule_method == 'annuity':
                principal = min(max(currency.round(instalment - interest), 0.0), balance)
            else:
                principal = min(currency.round(principal_per_period), balance)
            values.append({
                'date': due,
                'opening_balance': balance,
                'principal': principal,
                'interest': interest,
                'rate': rate,
            })
            balance = currency.round(balance - principal)
            previous = max(previous, due)
        return values

    def _imported_schedule_values(self, kept):
        """ The unpaid lines of an imported schedule, as imported or changed by hand. The principal repaid
        early comes off the last lines (the loan ends earlier); the last line repays what is left. """
        self.ensure_one()
        currency = self.currency_id
        lines = (self.line_ids - kept).sorted('sequence')
        events = self._principal_events()
        previous, balance = self._schedule_start(kept, events)
        balance = currency.round(balance + sum(amount for day, amount, _settles in events if day > previous))
        values = [{
            'date': line.date,
            'opening_balance': line.opening_balance,
            'principal': line.principal,
            'interest': line.interest,
            'rate': line.rate,
        } for line in lines]
        excess = currency.round(sum(vals['principal'] for vals in values) - balance)
        while values and currency.compare_amounts(excess, 0.0) > 0:
            cut = min(values[-1]['principal'], excess)
            values[-1]['principal'] = currency.round(values[-1]['principal'] - cut)
            excess = currency.round(excess - cut)
            if currency.is_zero(values[-1]['principal']):
                values.pop()
        return values

    def _generate_schedule(self, date_from=None):
        """ Compute the unpaid lines again, from the principal drawn, keeping the paid lines (and the unpaid
        lines due before `date_from`, when given). """
        for loan in self:
            kept = loan._kept_lines(date_from)
            values = loan._compute_schedule_values(kept)
            lines = (loan.line_ids - kept).sorted('sequence')
            commands = []
            for number, vals in enumerate(values, start=len(kept) + 1):
                vals = {**vals, 'sequence': number}
                if lines:
                    commands.append(Command.update(lines[0].id, vals))
                    lines = lines[1:]
                else:
                    commands.append(Command.create(vals))
            commands += [Command.unlink(line.id) for line in lines]
            loan.with_context(loan_schedule_update=True).line_ids = commands
            if loan.schedule_method == 'imported' and loan.payment_count != len(kept) + len(values):
                loan.with_context(loan_no_regenerate=True).payment_count = max(len(kept) + len(values), 1)
            loan._chain_balances()

    def _regenerate_from(self, rate_date):
        """ Compute again the unpaid lines of the running loans that a rate changing on `rate_date` changes:
        those due after it, or on it with the actual days (their last day accrues at the new rate). """
        for loan in self.filtered(lambda loan: loan.state == 'running' and loan.line_ids):
            date_from = rate_date and (rate_date if loan.interest_method == 'actual_365' else rate_date + ONE_DAY)
            loan._generate_schedule(date_from=date_from)

    def _chain_balances(self):
        """ Chain the opening and closing balances of the unpaid lines, the last one repaying the balance left
        (it takes the residue of the rounding and of the changes made by hand). """
        for loan in self:
            currency = loan.currency_id
            lines = loan.line_ids.sorted('sequence')
            kept = lines.filtered(lambda line: line.state == 'posted')
            unpaid = lines - kept
            if not unpaid:
                continue
            events = loan._principal_events()
            previous, balance = loan._schedule_start(loan._kept_lines(), events)
            updates = []
            for line in unpaid:
                balance += sum(amount for day, amount, _settles in events if previous < day <= line.date)
                balance = currency.round(balance)
                principal = balance if line == unpaid[-1] else line.principal
                if currency.compare_amounts(principal, 0.0) < 0:
                    raise UserError(self.env._(
                        'The principal of the lines exceeds the balance of the loan %s: lower it.',
                        loan.display_name))
                vals = {}
                if currency.compare_amounts(line.opening_balance, balance):
                    vals['opening_balance'] = balance
                if currency.compare_amounts(line.principal, principal):
                    vals['principal'] = principal
                if vals:
                    updates.append((line, vals))
                balance = currency.round(balance - principal)
                previous = max(previous, line.date)
            for line, vals in updates:
                line.with_context(loan_schedule_update=True).write(vals)

    # ------------------------------------------------------------
    # Balances at a date
    # ------------------------------------------------------------

    def _lines_unpaid_at(self, day):
        """ The lines not paid on `day`. """
        return self.line_ids.filtered(lambda line: line.state != 'posted' or line.payment_date > day).sorted('sequence')

    def _outstanding_at(self, day):
        """ The principal drawn and not repaid on `day`, in the currency of the loan. """
        self.ensure_one()
        events = self._principal_events(projection=False)
        paid = self.line_ids.filtered(lambda line: line.state == 'posted' and line.payment_date <= day)
        return self.currency_id.round(
            sum(amount for event_day, amount, _settles in events if event_day <= day) - sum(paid.mapped('principal')))

    def _principal_due_within(self, day, months=12):
        """ The principal not paid on `day` and due within `months` months after it, in the loan currency. """
        self.ensure_one()
        limit = day + relativedelta(months=months)
        due = sum(self._lines_unpaid_at(day).filtered(lambda line: line.date <= limit).mapped('principal'))
        return min(self.currency_id.round(due), max(self._outstanding_at(day), 0.0))

    def _accrued_interest_at(self, day):
        """ The interest accrued and not due on `day`: since the last due date, early repayment or the first
        drawdown. """
        self.ensure_one()
        events = self._principal_events(projection=False)
        starts = [line.date for line in self.line_ids if line.date <= day]
        starts += [event_day for event_day, _amount, settles in events if settles and event_day <= day]
        if not events or events[0][0] > day:
            return 0.0
        start = max(starts) if starts else events[0][0]
        balance = (sum(amount for event_day, amount, _settles in events if event_day <= start)
                   - sum(self.line_ids.filtered(lambda line: line.date <= start).mapped('principal')))
        later = self.line_ids.filtered(lambda line: line.date > day).sorted('sequence')[:1]
        index = later.sequence - 1 if later else len(self.line_ids)
        interest, _balance = self._interest_for(
            start, day, balance, [event for event in events if start < event[0] <= day],
            self._rate_at(start + ONE_DAY), self._period_days(index))
        return self.currency_id.round(max(interest, 0.0))

    def _account_balance_at(self, account, day, company_currency=False):
        """ The credit balance of `account` in the entries of the loan up to `day`, in the loan currency (or
        in the company currency). """
        self.ensure_one()
        lines = self.env['account.move.line'].search(Domain([
            ('move_id.loan_id', '=', self.id),
            ('account_id', '=', account.id),
            ('parent_state', '=', 'posted'),
            ('date', '<=', day),
        ]))
        if company_currency:
            return -self.company_id.currency_id.round(sum(lines.mapped('balance')))
        return -self.currency_id.round(sum(lines.mapped('amount_currency')))

    # ------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------

    def _bank_account(self, journal, direction):
        """ The account of the bank leg of an entry in `journal`: the outstanding receipts (direction
        'inbound') or payments ('outbound') account of the journal, which the bank statement line is matched
        with, or the bank account itself when the loan posts there. """
        self.ensure_one()
        if self.bank_posting == 'bank':
            account = journal.default_account_id
        else:
            method_lines = journal[f'{direction}_payment_method_line_ids']
            account = method_lines.payment_account_id[:1]
            if not account:
                xmlid = ('account_journal_payment_debit_account_id' if direction == 'inbound'
                         else 'account_journal_payment_credit_account_id')
                account = self.env['account.chart.template'].with_company(journal.company_id).ref(
                    xmlid, raise_if_not_found=False)
        if not account:
            raise UserError(self.env._(
                'The journal %s has no outstanding account: set one on its payment methods.', journal.display_name))
        return account

    def _principal_lines(self, amount, day, label):
        """ The debits repaying `amount` of principal on `day`: the short-term account first, as far as the
        reclassifications moved principal there, then the long-term account. """
        self.ensure_one()
        short_term = min(amount, max(self._account_balance_at(self.account_short_term_id, day), 0.0))
        return [
            (self.account_short_term_id, short_term, label),
            (self.account_long_term_id, self.currency_id.round(amount - short_term), label),
        ]

    def _create_move(self, journal, day, lines, entry_type, ref):
        """ Post an entry of the loan.

        :param lines: list of (account, amount in the loan currency, debit if positive, label[, extra values of
            the line]); the last line balances the entry, in the loan currency and in the company currency
        """
        self.ensure_one()
        currency = self.currency_id
        company_currency = self.company_id.currency_id
        lines = [line for line in lines[:-1] if not currency.is_zero(line[1])] + lines[-1:]
        total_currency = total_balance = 0.0
        commands = []
        for position, (account, amount, label, *extra) in enumerate(lines):
            if position == len(lines) - 1:
                amount, balance = -total_currency, -total_balance
            else:
                balance = currency._convert(amount, company_currency, self.company_id, day)
                total_currency += amount
                total_balance += balance
            commands.append(Command.create({
                'account_id': account.id,
                'partner_id': self.partner_id.id,
                'name': label,
                'currency_id': currency.id,
                'amount_currency': amount,
                'balance': balance,
                **(extra[0] if extra else {}),
            }))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': day,
            'ref': ref,
            'partner_id': self.partner_id.id,
            'currency_id': currency.id,
            'loan_id': self.id,
            'loan_entry_type': entry_type,
            'line_ids': commands,
        })
        move.action_post()
        return move

    # ------------------------------------------------------------
    # Leases
    # ------------------------------------------------------------

    def _rou_account(self):
        """ The account debited by the initial recognition of the lease. """
        self.ensure_one()
        return self.account_rou_id

    def _recognition(self):
        """ The posted initial recognition of the lease. """
        self.ensure_one()
        return self.operation_ids.filtered(lambda op: op.operation_type == 'recognition' and op.state == 'posted')

    def _recognize_lease(self):
        """ Post the initial recognition of the lease on its start date: Dr right-of-use asset / Cr long-term
        lease liability, at the present value of the lease payments.

        :return: the account.loan.operation of the recognition
        """
        self.ensure_one()
        currency = self.currency_id
        if currency.compare_amounts(self.principal, 0.0) <= 0:
            raise UserError(self.env._('The lease %s has no liability to recognize.', self.display_name))
        label = self.env._('%(lease)s - Initial recognition', lease=self.name)
        move = self._create_move(self.journal_id, self.date_start, [
            (self._rou_account(), self.principal, label),
            (self.account_long_term_id, 0.0, label),
        ], 'recognition', label)
        operation = self.env['account.loan.operation'].create({
            'loan_id': self.id,
            'operation_type': 'recognition',
            'date': self.date_start,
            'amount': self.principal,
            'journal_id': self.journal_id.id,
            'move_id': move.id,
        })
        self.message_post(body=self.env._(
            'Lease liability of %(amount)s recognized on %(date)s.',
            amount=currency.format(self.principal), date=self.date_start))
        return operation

    # ------------------------------------------------------------
    # Withholding tax
    # ------------------------------------------------------------

    def _withholding_details(self, base):
        """ The tax withheld on the interest `base`, computed by the withholding tax.

        :return: list of (account.tax.repartition.line, amount withheld, positive), in the loan currency
        """
        self.ensure_one()
        tax = self.withholding_tax_id
        currency = self.currency_id
        if not tax or currency.compare_amounts(base, 0.0) <= 0:
            return []
        # the tax computation itself: the withholding taxes deferred to the payments by the localizations are
        # filtered out of the documents only, not of this one
        computation = tax._get_tax_details(price_unit=base, quantity=1.0, precision_rounding=currency.rounding)
        details = []
        for tax_data in computation['taxes_data']:
            if tax_data.get('is_reverse_charge'):
                continue
            repartition = tax_data['tax'].invoice_repartition_line_ids.filtered(
                lambda rep: rep.repartition_type == 'tax' and rep.factor >= 0)
            for rep in repartition:
                details.append((rep, currency.round(-tax_data['tax_amount'] * rep.factor)))
        return details

    def _withholding_amount(self, base):
        """ The tax withheld on the interest `base`, in the loan currency. """
        self.ensure_one()
        return self.currency_id.round(sum(amount for _rep, amount in self._withholding_details(base)))

    def _interest_line_values(self):
        """ The extra values of the interest line of a payment: the base tags of the withholding tax. """
        self.ensure_one()
        tags = self.withholding_tax_id.invoice_repartition_line_ids.filtered(
            lambda rep: rep.repartition_type == 'base').tag_ids
        return {'tax_tag_ids': [Command.set(tags.ids)]} if tags else {}

    def _withholding_lines(self, base, withheld, day, label):
        """ The lines crediting the tax withheld on the interest `base` to the accounts of the tax, as tax lines
        of the tax: `withheld` may differ from the computation, the difference goes on the last line.

        :return: list of (account, amount, label, extra values) for `_create_move`
        """
        self.ensure_one()
        currency = self.currency_id
        details = self._withholding_details(base)
        if not details or currency.is_zero(withheld):
            return []
        difference = withheld - sum(amount for _rep, amount in details)
        details[-1] = (details[-1][0], currency.round(details[-1][1] + difference))
        base_balance = currency._convert(base, self.company_id.currency_id, self.company_id, day)
        lines = []
        for rep, amount in details:
            if not rep.account_id:
                raise UserError(self.env._(
                    'Set an account on the distribution of the withholding tax %s.', rep.tax_id.display_name))
            lines.append((rep.account_id, -amount, label, {
                'tax_repartition_line_id': rep.id,
                'tax_tag_ids': [Command.set(rep.tag_ids.ids)],
                'tax_base_amount': base_balance,
            }))
        return lines

    def _check_paid_up_to(self, day):
        """ Refuse an operation dated on or before the due date of a paid line. """
        self.ensure_one()
        paid = self.line_ids.filtered(lambda line: line.state == 'posted')
        if paid and day <= max(paid.mapped('date')):
            raise UserError(self.env._(
                'The loan %(loan)s is paid up to %(date)s: date the operation after it.',
                loan=self.display_name, date=max(paid.mapped('date'))))

    def _update_state(self):
        """ Close the loans fully repaid, open again the others. """
        for loan in self.filtered(lambda loan: loan.state in ('running', 'closed')):
            done = (loan.drawn_amount and loan.currency_id.is_zero(loan.outstanding_amount)
                    and not loan.line_ids.filtered(lambda line: line.state == 'draft'))
            state = 'closed' if done else 'running'
            if loan.state != state:
                loan.state = state

    # ------------------------------------------------------------
    # Reclassification
    # ------------------------------------------------------------

    def _reclassification_amount(self, day):
        """ What moves from the long-term to the short-term account on `day` (negative: back) so that the
        short-term account holds the principal due within 12 months. """
        self.ensure_one()
        target = self._principal_due_within(day)
        return self.currency_id.round(target - self._account_balance_at(self.account_short_term_id, day))

    def _reclassify(self, day, journal=None):
        """ Post the reclassification of the loan on `day`; nothing when the short-term balance is right.

        :return: the entry, or an empty recordset
        """
        self.ensure_one()
        later = self.move_ids.filtered(
            lambda move: move.loan_entry_type == 'reclassification' and move.state == 'posted' and move.date > day)
        if later:
            raise UserError(self.env._(
                'The loan %(loan)s is already reclassified on %(date)s: reclassify in the order of the dates.',
                loan=self.display_name, date=max(later.mapped('date'))))
        draft_bills = self.move_ids.filtered(
            lambda move: move.loan_entry_type == 'bill' and move.state == 'draft' and move.date <= day)
        if draft_bills:
            raise UserError(self.env._(
                'Post the bills of the lease %(lease)s dated up to %(date)s first.', lease=self.display_name, date=day))
        amount = self._reclassification_amount(day)
        if self.currency_id.is_zero(amount):
            return self.env['account.move']
        label = self.env._('%(loan)s - Principal due within 12 months', loan=self.name)
        return self._create_move(
            journal or self.journal_id, day,
            [(self.account_long_term_id, amount, label), (self.account_short_term_id, -amount, label)],
            'reclassification', self.env._('%(loan)s - Reclassification', loan=self.name))

    # ------------------------------------------------------------
    # Demo
    # ------------------------------------------------------------

    @api.model
    def _load_demo_loan(self):
        """ A bank loan for the demo: drawn in two tranches, the instalments due paid, reclassified at the end
        of the last month; an equipment loan and an office lease too. """
        company = self.env.company
        if not company.chart_template or self.search_count([('company_id', '=', company.id)], limit=1):
            return
        try:
            with self.env.cr.savepoint():
                self._demo_loan(company)
        except Exception:  # the demo is not worth failing the installation
            _logger.exception('Error while creating the demo loan of %s', company.name)

    @api.model
    def _demo_loan(self, company):
        self._demo_configure(company)
        today = fields.Date.context_today(self)
        month_end = today + relativedelta(day=1) - ONE_DAY
        Partner = self.env['res.partner']
        start = today + relativedelta(months=-7, day=1)
        loan = self.create({
            'partner_id': Partner.create({'name': 'Harbor Commercial Bank', 'is_company': True}).id,
            'lender_ref': 'TL-2026-0417',
            'principal': 120000.0,
            'date_start': start,
            'date_first_payment': start + relativedelta(months=1, day=31),
            'payment_count': 36,
            'rate_type': 'floating',
            'rate': 6.0,
            'rate_line_ids': [Command.create({'date': start + relativedelta(months=4), 'rate': 6.5})],
        })
        loan.action_confirm()
        self._demo_draw(loan, start, 80000.0)
        self._demo_draw(loan, start + relativedelta(months=2, day=10), 40000.0)
        start = today + relativedelta(months=-14, day=1)
        equipment = self.create({
            'partner_id': Partner.create({'name': 'Northgate Equipment Finance', 'is_company': True}).id,
            'lender_ref': 'EQ-88231',
            'principal': 60000.0,
            'date_start': start,
            'payment_frequency': 'quarterly',
            'payment_count': 20,
            'rate': 5.25,
            'schedule_method': 'fixed_principal',
            'interest_method': 'actual_365',
        })
        equipment.action_confirm()
        self._demo_draw(equipment, start, 60000.0)
        lease = self.create({
            'loan_type': 'lease',
            'partner_id': Partner.create({'name': 'Riverside Office Properties', 'is_company': True}).id,
            'lender_ref': 'OFFICE-3F-2026',
            'lease_payment': 2500.0,
            'date_start': today + relativedelta(months=-5, day=1),
            'payment_count': 36,
            'rate': 5.0,
        })
        lease.action_confirm()
        loans = loan | equipment
        self._demo_pay(loans, month_end)
        self._demo_bill(lease, month_end)
        for record in loans | lease:
            record._reclassify(month_end)
        self._demo_pay(loans, today - ONE_DAY)
        self._demo_bill(lease, today - ONE_DAY)

    @api.model
    def _demo_draw(self, loan, day, amount):
        self.env['account.loan.drawdown'].create({'loan_id': loan.id, 'date': day, 'amount': amount}).action_confirm()

    @api.model
    def _demo_pay(self, loans, until):
        lines = loans.line_ids.filtered(lambda line: line.state == 'draft' and line.date <= until)
        for line in lines.sorted(lambda line: (line.date, line.sequence)):
            self.env['account.loan.pay'].create({'line_id': line.id}).action_confirm()

    @api.model
    def _demo_bill(self, leases, until):
        lines = leases.line_ids.filtered(lambda line: line.state == 'draft' and line.date <= until)
        for line in lines.sorted(lambda line: (line.date, line.sequence)):
            line._create_bill()

    @api.model
    def _demo_configure(self, company):
        """ The loan accounts and journals of the demo company, created when the chart has none. """
        Account = self.env['account.account'].with_company(company)
        domain = Account._check_company_domain(company)

        def account(xmlid, name, account_type):
            found = self.env.ref(f'om_account_loan.{xmlid}_{company.id}', raise_if_not_found=False)
            if found:
                return found
            code = Account._search_new_account_code(
                Account.search([*domain, ('account_type', '=', account_type)], limit=1).code or '2900')
            record = Account.create({'name': name, 'code': code, 'account_type': account_type})
            self.env['ir.model.data'].create({
                'module': 'om_account_loan', 'name': f'{xmlid}_{company.id}', 'model': 'account.account',
                'res_id': record.id, 'noupdate': True})
            return record

        Journal = self.env['account.journal'].with_company(company)
        company.write({
            'loan_long_term_account_id': (company.loan_long_term_account_id or account(
                'demo_loan_long_term', 'Bank Loans (non-current)', 'liability_non_current')).id,
            'loan_short_term_account_id': (company.loan_short_term_account_id or account(
                'demo_loan_short_term', 'Bank Loans (current)', 'liability_current')).id,
            'loan_interest_account_id': (company.loan_interest_account_id or account(
                'demo_loan_interest', 'Interest on Loans', 'expense')).id,
            'loan_journal_id': (company.loan_journal_id or Journal.search(
                [*Journal._check_company_domain(company), ('type', '=', 'general')], limit=1)).id,
            'loan_bank_journal_id': (company.loan_bank_journal_id or Journal.search(
                [*Journal._check_company_domain(company), ('type', '=', 'bank')], limit=1)).id,
            'lease_long_term_account_id': (company.lease_long_term_account_id or account(
                'demo_lease_long_term', 'Lease Liabilities (non-current)', 'liability_non_current')).id,
            'lease_short_term_account_id': (company.lease_short_term_account_id or account(
                'demo_lease_short_term', 'Lease Liabilities (current)', 'liability_current')).id,
            'lease_rou_account_id': (company.lease_rou_account_id or account(
                'demo_lease_rou', 'Right-of-use Assets', 'asset_non_current')).id,
            'lease_bill_journal_id': (company.lease_bill_journal_id or Journal.search(
                [*Journal._check_company_domain(company), ('type', '=', 'purchase')], limit=1)).id,
        })
