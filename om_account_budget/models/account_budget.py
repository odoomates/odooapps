from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# computed, non-stored amounts that read_group() aggregates by hand
COMPUTED_AMOUNT_FIELDS = ('practical_amount', 'theoritical_amount', 'percentage')


class AccountBudgetPost(models.Model):
    _name = "account.budget.post"
    _order = "name"
    _description = "Budgetary Position"

    name = fields.Char('Name', required=True)
    account_ids = fields.Many2many(
        'account.account', 'account_budget_rel', 'budget_id',
        'account_id', 'Accounts',
        domain=[('deprecated', '=', False)]
    )
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)

    def _check_account_ids(self, vals):
        # Raise an error to prevent the account.budget.post to have not specified account_ids.
        # This check is done on create because require=True doesn't work on Many2many fields.
        if 'account_ids' in vals:
            account_ids = self.new({'account_ids': vals['account_ids']}, origin=self).account_ids
        else:
            account_ids = self.account_ids
        if not account_ids:
            raise ValidationError(_('The budget must have at least one account.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_account_ids(vals)
        return super(AccountBudgetPost, self).create(vals_list)

    def write(self, vals):
        self._check_account_ids(vals)
        return super(AccountBudgetPost, self).write(vals)


class CrossoveredBudget(models.Model):
    _name = "crossovered.budget"
    _description = "Budget"
    _inherit = ['mail.thread']

    name = fields.Char('Budget Name', required=True)
    user_id = fields.Many2one('res.users', 'Responsible', default=lambda self: self.env.user)
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('validate', 'Validated'),
        ('done', 'Done')
        ], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, tracking=True)
    crossovered_budget_line = fields.One2many(
        'crossovered.budget.lines', 'crossovered_budget_id',
        'Budget Lines', copy=True
    )
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)

    def action_budget_confirm(self):
        self.write({'state': 'confirm'})

    def action_budget_draft(self):
        self.write({'state': 'draft'})

    def action_budget_validate(self):
        self.write({'state': 'validate'})

    def action_budget_cancel(self):
        self.write({'state': 'cancel'})

    def action_budget_done(self):
        self.write({'state': 'done'})


class CrossoveredBudgetLines(models.Model):
    _name = "crossovered.budget.lines"
    _description = "Budget Line"

    name = fields.Char(compute='_compute_line_name')
    crossovered_budget_id = fields.Many2one('crossovered.budget', 'Budget', ondelete='cascade', index=True, required=True)
    analytic_account_id = fields.Many2one('account.analytic.account', 'Analytic Account')
    # account.analytic.group no longer exists: analytic_account_id.plan_id points at
    # account.analytic.plan, and a wrong comodel makes fields_get() raise a KeyError
    analytic_plan_id = fields.Many2one('account.analytic.plan', 'Analytic Plan', related='analytic_account_id.plan_id', readonly=True)
    general_budget_id = fields.Many2one('account.budget.post', 'Budgetary Position')
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    paid_date = fields.Date('Paid Date')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    planned_amount = fields.Monetary(
        'Planned Amount', required=True,
        help="Amount you plan to earn/spend. Record a positive amount if it is a revenue and a negative amount if it is a cost.")
    practical_amount = fields.Monetary(
        compute='_compute_practical_amount', string='Practical Amount', help="Amount really earned/spent.")
    theoritical_amount = fields.Monetary(
        compute='_compute_theoritical_amount', string='Theoretical Amount',
        help="Amount you are supposed to have earned/spent at this date.")
    percentage = fields.Float(
        compute='_compute_percentage', string='Achievement',
        help="Comparison between practical and theoretical amount. This measure tells you if you are below or over budget.")
    company_id = fields.Many2one(related='crossovered_budget_id.company_id', comodel_name='res.company',
        string='Company', store=True, readonly=True)
    is_above_budget = fields.Boolean(compute='_is_above_budget')
    crossovered_budget_state = fields.Selection(related='crossovered_budget_id.state', string='Budget State', store=True, readonly=True)

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        # practical_amount, theoritical_amount and percentage are computed and not
        # stored, so the ORM does not advertise a group_operator for them. Without one
        # the pivot and graph views refuse them as measures ("No aggregate function
        # has been provided for the measure ...") and the list view shows no group
        # totals. read_group() below computes them by hand, so tell the client they
        # can be aggregated.
        if attributes is None or 'group_operator' in attributes:
            for fname in COMPUTED_AMOUNT_FIELDS:
                if fname in res:
                    res[fname]['group_operator'] = 'sum'
        return res

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        # overrides the default read_group in order to compute the computed fields manually for the group.
        # A field is asked as `field`, `field:agg` or, by the spreadsheets, `name:agg(field)`: the value of a
        # computed one is returned under its name.
        computed = {}
        stored = []
        for spec in fields:
            name, __, aggregate = spec.partition(':')
            field_name = aggregate[aggregate.index('(') + 1:-1] if '(' in aggregate else name
            if field_name in COMPUTED_AMOUNT_FIELDS:
                computed[name] = field_name
            else:
                stored.append(spec)
        result = super(CrossoveredBudgetLines, self).read_group(domain, stored, groupby, offset=offset, limit=limit,
                                                                orderby=orderby, lazy=lazy)
        if computed:
            for group_line in result:
                lines = self.search(group_line['__domain'] if '__domain' in group_line else domain)
                practical = sum(lines.mapped('practical_amount'))
                theoritical = sum(lines.mapped('theoritical_amount'))
                values = {
                    'practical_amount': practical,
                    'theoritical_amount': theoritical,
                    # weighted average, as a ratio like _compute_percentage: the views render it with
                    # widget="percentage", which is what turns it into a percentage
                    'percentage': float(practical / theoritical) if theoritical else 0,
                }
                for name, field_name in computed.items():
                    group_line[name] = values[field_name]
                if 'percentage' in computed.values():
                    # the amounts the percentage is made of, as before
                    group_line.setdefault('practical_amount', practical)
                    group_line.setdefault('theoritical_amount', theoritical)
        return result

    def _is_above_budget(self):
        for line in self:
            if line.theoritical_amount >= 0:
                line.is_above_budget = line.practical_amount > line.theoritical_amount
            else:
                line.is_above_budget = line.practical_amount < line.theoritical_amount

    def _compute_line_name(self):
        #just in case someone opens the budget line in form view
        for line in self:
            computed_name = line.crossovered_budget_id.name
            if line.general_budget_id:
                computed_name += ' - ' + line.general_budget_id.name
            if line.analytic_account_id:
                computed_name += ' - ' + line.analytic_account_id.name
            line.name = computed_name

    def _get_practical_amount_key(self):
        """ Lines with the same key are computed by a single query. """
        self.ensure_one()
        accounts = tuple(sorted(self.general_budget_id.account_ids.ids))
        period = (self.date_from, self.date_to, self.company_id.id)
        if self.analytic_account_id:
            # Odoo 16 keeps the analytic account of every plan in account_id
            return ('analytic', 'account_id', accounts, *period)
        return ('journal', accounts, *period)

    def _compute_practical_amount(self):
        lines_by_key = defaultdict(lambda: self.browse())
        amounts = {}
        for line in self:
            amounts[line] = 0.0
            if line.date_from and line.date_to and (line.analytic_account_id or line.general_budget_id):
                lines_by_key[line._get_practical_amount_key()] |= line

        for key, lines in lines_by_key.items():
            if key[0] == 'analytic':
                dummy, column, accounts, date_from, date_to, company_id = key
                domain = [
                    (column, 'in', lines.analytic_account_id.ids),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                    ('company_id', 'in', [company_id, False]),
                ]
                if accounts:
                    domain.append(('general_account_id', 'in', list(accounts)))
                totals = {group[column][0]: group['amount'] for group in self.env['account.analytic.line'].read_group(
                    domain, ['amount:sum'], [column])}
                for line in lines:
                    amounts[line] = totals.get(line.analytic_account_id.id, 0.0)
            else:
                dummy, accounts, date_from, date_to, company_id = key
                if not accounts:
                    continue
                # the budget belongs to one company and only posted entries have actually
                # been spent/earned
                [group] = self.env['account.move.line'].read_group([
                    ('account_id', 'in', list(accounts)),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                    ('company_id', '=', company_id),
                    ('parent_state', '=', 'posted'),
                ], ['credit:sum', 'debit:sum'], [])
                credit, debit = group['credit'], group['debit']
                for line in lines:
                    amounts[line] = (credit or 0.0) - (debit or 0.0)

        for line, amount in amounts.items():
            line.practical_amount = amount

    def _compute_theoritical_amount(self):
        # beware: 'today' variable is mocked in the python tests and thus, its implementation matter
        today = fields.Date.today()
        for line in self:
            if line.paid_date:
                if today <= line.paid_date:
                    theo_amt = 0.00
                else:
                    theo_amt = line.planned_amount
            else:
                theo_amt = 0.00
                if line.date_from and line.date_to:
                    line_timedelta = line.date_to - line.date_from
                    elapsed_timedelta = today - line.date_from

                    if elapsed_timedelta.days < 0:
                        # If the budget line has not started yet, theoretical amount should be zero
                        theo_amt = 0.00
                    elif line_timedelta.days > 0 and today < line.date_to:
                        # If today is between the budget line date_from and date_to
                        theo_amt = (elapsed_timedelta.total_seconds() / line_timedelta.total_seconds()) * line.planned_amount
                    else:
                        theo_amt = line.planned_amount
            line.theoritical_amount = theo_amt

    def _compute_percentage(self):
        for line in self:
            if line.theoritical_amount != 0.00:
                line.percentage = float((line.practical_amount or 0.0) / line.theoritical_amount)
            else:
                line.percentage = 0.00

    # crossovered_budget_id is in the tuple so the check runs on create: a constraint
    # only fires for the fields the values carry, and a line created with neither a
    # position nor an analytic account carries neither of them
    @api.constrains('general_budget_id', 'analytic_account_id', 'crossovered_budget_id')
    def _must_have_analytical_or_budgetary_or_both(self):
        # constraints are called with the whole recordset: never touch a field on self
        for line in self:
            if not line.analytic_account_id and not line.general_budget_id:
                raise ValidationError(
                    _("You have to enter at least a budgetary position or analytic account on a budget line."))

    def action_open_budget_entries(self):
        self.ensure_one()
        if self.analytic_account_id:
            # if there is an analytic account, then the analytic items are loaded
            action = self.env['ir.actions.act_window']._for_xml_id('analytic.account_analytic_line_action_entries')
            action['domain'] = [('account_id', '=', self.analytic_account_id.id),
                                ('date', '>=', self.date_from),
                                ('date', '<=', self.date_to)
                                ]
            if self.general_budget_id:
                action['domain'] += [('general_account_id', 'in', self.general_budget_id.account_ids.ids)]
        else:
            # otherwise the journal entries booked on the accounts of the budgetary postition are opened
            action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_moves_all_a')
            action['domain'] = [('account_id', 'in',
                                 self.general_budget_id.account_ids.ids),
                                ('date', '>=', self.date_from),
                                ('date', '<=', self.date_to)
                                ]
        return action

    @api.constrains('date_from', 'date_to')
    def _line_dates_between_budget_dates(self):
        for rec in self:
            budget_date_from = rec.crossovered_budget_id.date_from
            budget_date_to = rec.crossovered_budget_id.date_to
            if rec.date_from:
                date_from = rec.date_from
                if date_from < budget_date_from or date_from > budget_date_to:
                    raise ValidationError(_('"Start Date" of the budget line should be included in the Period of the budget'))
            if rec.date_to:
                date_to = rec.date_to
                if date_to < budget_date_from or date_to > budget_date_to:
                    raise ValidationError(_('"End Date" of the budget line should be included in the Period of the budget'))
