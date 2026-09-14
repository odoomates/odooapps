from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from .account_budget_position import BUDGET_TYPES

COMPUTED_AMOUNT_FIELDS = {'practical_amount', 'theoretical_amount', 'achievement'}


class AccountBudgetLine(models.Model):
    _name = 'account.budget.line'
    _description = 'Budget Line'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(compute='_compute_line_name')
    sequence = fields.Integer(default=10)
    budget_id = fields.Many2one('account.budget', 'Budget', ondelete='cascade', index=True, required=True)
    analytic_account_id = fields.Many2one('account.analytic.account', 'Analytic Account', check_company=True)
    analytic_plan_id = fields.Many2one(related='analytic_account_id.plan_id')
    position_id = fields.Many2one('account.budget.position', 'Budgetary Position', check_company=True)
    budget_type = fields.Selection(
        BUDGET_TYPES, string='Type', required=True,
        compute='_compute_budget_type', store=True, readonly=False, precompute=True,
        help="Expense lines plan costs, revenue lines plan incomes. Planned amounts are always positive.",
    )
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    distribution = fields.Selection(
        [('spread', 'Spread Evenly'), ('at_date', 'At a Date')],
        string='Expected', required=True, default='spread',
        help="Spread Evenly: the amount is expected little by little over the period.\n"
             "At a Date: the whole amount is expected on the planned date, e.g. a yearly fee.",
    )
    planned_date = fields.Date('Planned Date')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    planned_amount = fields.Monetary(
        'Planned Amount', required=True,
        help="Amount you plan to spend (expense lines) or to earn (revenue lines).")
    practical_amount = fields.Monetary(
        compute='_compute_practical_amount', string='Actual Amount',
        help="Amount really spent or earned, from the posted journal entries.")
    theoretical_amount = fields.Monetary(
        compute='_compute_theoretical_amount', string='Theoretical Amount',
        help="Amount you are supposed to have spent or earned at this date.")
    achievement = fields.Float(
        compute='_compute_achievement', string='Achievement',
        help="Actual amount compared with the theoretical amount.")
    company_id = fields.Many2one(related='budget_id.company_id', comodel_name='res.company',
                                 string='Company', store=True, readonly=True)
    is_above_budget = fields.Boolean(compute='_compute_is_above_budget')
    is_over_budget = fields.Boolean(
        'Over Budget', compute='_compute_is_above_budget', search='_search_is_over_budget',
        help="Expense line which spent more than its theoretical amount.")
    budget_state = fields.Selection(related='budget_id.state', string='Budget State', store=True, readonly=True)
    warning_level = fields.Selection(
        [('none', 'None'), ('threshold', 'Threshold Reached'), ('exceeded', 'Exceeded')],
        default='none', copy=False, readonly=True,
        help="Technical field: last warning sent to the responsible of the budget.")

    # -------------------------------------------------------------------------
    # COMPUTE
    # -------------------------------------------------------------------------

    @api.depends('position_id')
    def _compute_budget_type(self):
        for line in self:
            if line.position_id:
                line.budget_type = line.position_id.budget_type
            elif not line.budget_type:
                line.budget_type = 'expense'

    def _compute_line_name(self):
        for line in self:
            names = [line.budget_id.name, line.position_id.name, line.analytic_account_id.name]
            line.name = ' - '.join(name for name in names if name)

    def _get_practical_amount_key(self):
        """ Lines with the same key are computed by a single query. """
        self.ensure_one()
        accounts = tuple(sorted(self.position_id.account_ids.ids))
        period = (self.date_from, self.date_to, self.company_id.id)
        if self.analytic_account_id:
            # since the analytic plans, each root plan stores its accounts in its own column
            return ('analytic', self.analytic_account_id.plan_id._column_name(), accounts, *period)
        return ('journal', accounts, *period)

    def _compute_practical_amount(self):
        lines_by_key = defaultdict(lambda: self.browse())
        balances = {}
        for line in self:
            balances[line] = 0.0
            if line.date_from and line.date_to and (line.analytic_account_id or line.position_id):
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
                amounts = dict(self.env['account.analytic.line']._read_group(
                    domain, groupby=[column], aggregates=['amount:sum']))
                for line in lines:
                    balances[line] = amounts.get(line.analytic_account_id, 0.0)
            else:
                dummy, accounts, date_from, date_to, company_id = key
                if not accounts:
                    continue
                [(balance,)] = self.env['account.move.line']._read_group([
                    ('account_id', 'in', list(accounts)),
                    ('date', '>=', date_from),
                    ('date', '<=', date_to),
                    ('company_id', '=', company_id),
                    ('parent_state', '=', 'posted'),
                ], aggregates=['balance:sum'])
                for line in lines:
                    balances[line] = -(balance or 0.0)

        for line, income in balances.items():
            # incomes are positive in the books, costs are counted positive on expense lines
            line.practical_amount = -income if line.budget_type == 'expense' else income

    def _compute_theoretical_amount(self):
        today = fields.Date.context_today(self)
        for line in self:
            amount = 0.0
            if line.distribution == 'at_date':
                if line.planned_date and today >= line.planned_date:
                    amount = line.planned_amount
            elif line.date_from and line.date_to and today >= line.date_from:
                # both dates of the period are included
                period_days = (line.date_to - line.date_from).days + 1
                elapsed_days = (min(today, line.date_to) - line.date_from).days + 1
                amount = line.planned_amount * elapsed_days / period_days
            line.theoretical_amount = amount

    def _compute_achievement(self):
        for line in self:
            line.achievement = line.practical_amount / line.theoretical_amount if line.theoretical_amount else 0.0

    def _compute_is_above_budget(self):
        for line in self:
            line.is_above_budget = line.currency_id.compare_amounts(line.practical_amount, line.theoretical_amount) > 0
            line.is_over_budget = line.budget_type == 'expense' and line.is_above_budget

    def _search_is_over_budget(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('Operation not supported.'))
        expense_lines = self.search([('budget_type', '=', 'expense')])
        over_budget_ids = expense_lines.filtered('is_over_budget').ids
        in_operator = 'in' if (operator == '=') == value else 'not in'
        return [('id', in_operator, over_budget_ids)]

    # -------------------------------------------------------------------------
    # GROUPED AMOUNTS
    # -------------------------------------------------------------------------

    def _split_computed_aggregates(self, aggregates):
        """ Split the aggregates on the non-stored computed amount fields, which
        cannot be aggregated in SQL, from the other ones.

        :return: (sql aggregates, {aggregate spec: field name})
        """
        computed_specs = {spec: spec.split(':', 1)[0] for spec in aggregates
                          if spec.split(':', 1)[0] in COMPUTED_AMOUNT_FIELDS}
        return [spec for spec in aggregates if spec not in computed_specs], computed_specs

    def _fill_computed_aggregates(self, domain, groups, computed_specs):
        """ Compute the non-stored amount fields manually for each group. """
        lines_by_group = [
            self.search(Domain(domain or []) & Domain(group.get('__extra_domain') or []))
            for group in groups
        ]
        # compute the amounts of all the lines at once, then sum them per group
        all_lines = self.browse().union(*lines_by_group)
        all_lines.mapped('practical_amount')
        all_lines.mapped('theoretical_amount')
        for group_line, lines in zip(groups, lines_by_group):
            practical_amount = sum(lines.mapped('practical_amount'))
            theoretical_amount = sum(lines.mapped('theoretical_amount'))
            values = {
                'practical_amount': practical_amount,
                'theoretical_amount': theoretical_amount,
                # same ratio as on the lines, weighted by the theoretical amounts
                'achievement': practical_amount / theoretical_amount if theoretical_amount else 0.0,
            }
            for spec, field_name in computed_specs.items():
                group_line[spec] = values[field_name]

    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        # overrides the default formatted_read_group in order to compute the computed fields manually for the group
        aggregates, computed_specs = self._split_computed_aggregates(aggregates)
        result = super().formatted_read_group(domain, groupby, aggregates, having=having,
                                              offset=offset, limit=limit, order=order)
        if computed_specs:
            self._fill_computed_aggregates(domain, result, computed_specs)
        return result

    @api.model
    def formatted_read_grouping_sets(self, domain, grouping_sets, aggregates=(), *, order=None):
        # same as formatted_read_group, used by the pivot view
        aggregates, computed_specs = self._split_computed_aggregates(aggregates)
        result = super().formatted_read_grouping_sets(domain, grouping_sets, aggregates, order=order)
        if computed_specs:
            for groups in result:
                self._fill_computed_aggregates(domain, groups, computed_specs)
        return result

    # -------------------------------------------------------------------------
    # CONSTRAINTS AND LOCK
    # -------------------------------------------------------------------------

    @api.constrains('position_id', 'analytic_account_id')
    def _check_position_or_analytic_account(self):
        for line in self:
            if not line.analytic_account_id and not line.position_id:
                raise ValidationError(
                    _("You have to enter at least a budgetary position or analytic account on a budget line."))

    @api.constrains('date_from', 'date_to', 'budget_id')
    def _check_dates(self):
        for line in self:
            budget = line.budget_id
            if line.date_from > line.date_to:
                raise ValidationError(_('The line "%s" must start before it ends.', line.name))
            if not (budget.date_from <= line.date_from <= budget.date_to) or not (budget.date_from <= line.date_to <= budget.date_to):
                raise ValidationError(_('The period of the line "%s" must be included in the period of the budget.', line.name))

    @api.constrains('planned_amount')
    def _check_planned_amount(self):
        for line in self:
            if line.currency_id.compare_amounts(line.planned_amount, 0.0) < 0:
                raise ValidationError(_(
                    'The planned amount of "%s" must be positive: choose whether the line is an expense or a revenue.',
                    line.name))

    @api.constrains('distribution', 'planned_date', 'date_from', 'date_to')
    def _check_planned_date(self):
        for line in self:
            if line.distribution == 'at_date' and not (line.planned_date and line.date_from <= line.planned_date <= line.date_to):
                raise ValidationError(_('Set a planned date within the period of the line "%s".', line.name))

    @api.constrains('budget_id', 'position_id', 'analytic_account_id', 'budget_type', 'date_from', 'date_to')
    def _check_overlap(self):
        """ Overlapping lines on the same position and analytic account count the same entries twice. """
        for budget in self.budget_id:
            seen = defaultdict(list)
            for line in budget.line_ids.sorted('date_from'):
                key = (line.position_id, line.analytic_account_id, line.budget_type)
                for other in seen[key]:
                    if line.date_from <= other.date_to and other.date_from <= line.date_to:
                        raise ValidationError(_(
                            'The lines "%(line)s" and "%(other)s" overlap: the same entries would be counted twice.',
                            line=line.name, other=other.name))
                seen[key].append(line)

    def _check_budget_is_draft(self):
        if self.env.context.get('budget_force_edit'):
            return
        locked = self.budget_id.filtered(lambda budget: budget.state != 'draft')
        if locked:
            raise UserError(_('Reset the budget "%s" to draft to change its lines.', locked[0].name))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_budget_is_draft()
        return lines

    def write(self, vals):
        self._check_budget_is_draft()
        result = super().write(vals)
        if 'budget_id' in vals:
            self._check_budget_is_draft()
        return result

    def unlink(self):
        self._check_budget_is_draft()
        return super().unlink()

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def action_open_budget_entries(self):
        self.ensure_one()
        if self.analytic_account_id:
            # if there is an analytic account, then the analytic items are loaded
            action = self.env['ir.actions.act_window']._for_xml_id('analytic.account_analytic_line_action_entries')
            column = self.analytic_account_id.plan_id._column_name()
            action['domain'] = [(column, '=', self.analytic_account_id.id),
                                ('date', '>=', self.date_from),
                                ('date', '<=', self.date_to)]
            if self.position_id:
                action['domain'] += [('general_account_id', 'in', self.position_id.account_ids.ids)]
        else:
            # otherwise the journal entries booked on the accounts of the budgetary position are opened
            action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_moves_all_a')
            action['domain'] = [('account_id', 'in', self.position_id.account_ids.ids),
                                ('date', '>=', self.date_from),
                                ('date', '<=', self.date_to),
                                ('company_id', '=', self.company_id.id),
                                ('parent_state', '=', 'posted')]
        return action

    def _get_period_chunks(self, period_months):
        """ Periods of `period_months` calendar months (1: months, 3: quarters) covering the line. """
        self.ensure_one()
        chunks = []
        start = self.date_from
        while start <= self.date_to:
            first_month = start.month - (start.month - 1) % period_months
            period_end = start.replace(month=first_month, day=1) + relativedelta(months=period_months, days=-1)
            end = min(period_end, self.date_to)
            chunks.append((start, end))
            start = end + relativedelta(days=1)
        return chunks

    def _split_by_period(self, period_months):
        """ Replace each line covering several periods by one line per period, the planned amount
        being shared according to the days of each period.

        :return: the new lines
        """
        vals_list = []
        lines_to_replace = self.browse()
        for line in self:
            chunks = line._get_period_chunks(period_months)
            if len(chunks) < 2:
                continue
            lines_to_replace |= line
            total_days = (line.date_to - line.date_from).days + 1
            remaining = line.planned_amount
            for index, (start, end) in enumerate(chunks):
                if index == len(chunks) - 1:
                    amount = remaining
                else:
                    amount = line.currency_id.round(line.planned_amount * ((end - start).days + 1) / total_days)
                    remaining -= amount
                holds_planned_date = bool(line.planned_date) and start <= line.planned_date <= end
                if line.distribution == 'at_date':
                    if not holds_planned_date:
                        continue
                    # the whole amount stays on the period of the planned date
                    amount = line.planned_amount
                vals_list.append({
                    **line.copy_data()[0],
                    'date_from': start,
                    'date_to': end,
                    'planned_amount': amount,
                    'distribution': 'at_date' if line.distribution == 'at_date' and holds_planned_date else 'spread',
                    'planned_date': line.planned_date if holds_planned_date else False,
                })
        lines_to_replace.unlink()
        return self.create(vals_list)
