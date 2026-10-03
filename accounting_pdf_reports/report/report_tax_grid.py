import ast
import re
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.float_utils import float_round
from odoo.tools.safe_eval import safe_eval

# a term of an aggregation formula: <line code>.<expression label>
TERM_REGEX = re.compile(r'(?<![\w.])(\w+)\.(_?[A-Za-z]\w*)')
# a term of an account codes formula: [sign] prefix [\(excluded prefixes)] [C|D]
ACCOUNT_CODES_REGEX = re.compile(r'([+-]?)\s*(\w+)(?:\\\(([\w,\s]*)\))?([CD]?)')
AMOUNT_REGEX = r'(?:[A-Z]{3}\()?\s*(-?[\d.]+)\s*\)?'


class ReportTaxGrid(models.AbstractModel):
    """ The tax return of a country as its localization lays it out (account.report, l10n_* modules): the tax
    grids are the tax tags of the journal items, the totals the aggregations of the grids. """
    _name = 'report.accounting_pdf_reports.report_tax_grid'
    _description = 'Tax Report by Tax Grid'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not data['form'].get('tax_grid_report_id'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the journal items are read from the database: write the pending changes first
        self.env.flush_all()
        form = data['form']
        report = self.env['account.report'].browse(form['tax_grid_report_id'])
        return {
            'data': form,
            'report': report,
            'columns': self._get_columns(report),
            'lines': self.get_lines(report, form),
        }

    @api.model
    def _get_columns(self, report):
        return [{'name': column.name, 'label': column.expression_label, 'figure_type': column.figure_type}
                for column in report.column_ids] or [{'name': _('Balance'), 'label': 'balance', 'figure_type': 'monetary'}]

    @api.model
    def get_lines(self, report, options):
        """ :return: the lines of the report in their order, each with its value per column """
        columns = self._get_columns(report)
        evaluator = _Evaluator(self.env, report, options)
        lines = []

        def walk(report_lines):
            for line in report_lines.sorted(lambda l: (l.sequence, l.id)):
                expressions = {expression.label: expression for expression in line.expression_ids}
                values = []
                for column in columns:
                    expression = expressions.get(column['label'])
                    value = evaluator.value(expression) if expression else None
                    if expression and expression.blank_if_zero and not value:
                        value = None
                    values.append({
                        'value': value,
                        'figure_type': expression and expression.figure_type or column['figure_type'] or 'monetary',
                    })
                lines.append({
                    'name': line.name,
                    'code': line.code,
                    'level': line.hierarchy_level,
                    'title': bool(line.children_ids) or not line.expression_ids,
                    'values': values,
                })
                walk(line.children_ids)

        walk(report.line_ids.filtered(lambda l: not l.parent_id))
        return lines


class _Evaluator:
    """ Computes the expressions of a report for a period, each once """

    def __init__(self, env, report, options):
        self.env = env
        self.report = report
        context = options.get('used_context') or {}
        self.company = env['res.company'].browse(context.get('company_id') or env.company.id)
        self.date_from = fields.Date.to_date(options['date_from'])
        self.date_to = fields.Date.to_date(options['date_to'])
        self.target_move = options.get('target_move', 'posted')
        self.journal_ids = context.get('journal_ids') or []
        self.country = report.country_id or self.company.account_fiscal_country_id
        self.cache = {}
        self.computing = set()
        # every expression the lines of the report depend on, of this report or of another one (cross_report)
        expressions = report.line_ids.expression_ids._expand_aggregations()
        self.by_code = {}
        for expression in expressions:
            line = expression.report_line_id
            if line.code:
                self.by_code[(line.report_id.id, line.code, expression.label)] = expression
        self._compute_tax_tags(expressions.filtered(lambda e: e.engine == 'tax_tags'))

    # the journal items --------------------------------------------------------------------------------------

    def _dates(self, date_scope):
        fiscal_year_start = self.company.compute_fiscalyear_dates(self.date_to)['date_from']
        return {
            'from_beginning': (None, self.date_to),
            'from_fiscalyear': (fiscal_year_start, self.date_to),
            'to_beginning_of_fiscalyear': (None, fiscal_year_start - relativedelta(days=1)),
            'to_beginning_of_period': (None, self.date_from - relativedelta(days=1)),
        }.get(date_scope, (self.date_from, self.date_to))

    def _domain(self, date_scope):
        MoveLine = self.env['account.move.line']
        date_from, date_to = self._dates(date_scope)
        domain = Domain([
            ('company_id', '=', self.company.id),
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('date', '<=', date_to),
        ])
        if date_from:
            domain &= Domain('date', '>=', date_from)
        if self.target_move == 'posted':
            domain &= Domain('parent_state', '=', 'posted')
        else:
            domain &= Domain('parent_state', '!=', 'cancel')
        if self.journal_ids:
            domain &= Domain('journal_id', 'in', self.journal_ids)
        if self.report.only_tax_exigible:
            # a cash basis tax is due when it is paid, on its cash basis entry
            domain &= MoveLine._get_tax_exigible_domain()
        return domain

    def _compute_tax_tags(self, expressions):
        """ The grids of all the tax_tags expressions, one query per date scope """
        Tag = self.env['account.account.tag']
        for date_scope, scope_expressions in expressions.grouped('date_scope').items():
            tags_by_expression = {
                expression: Tag._get_tax_tags(expression.formula, (expression.report_line_id.report_id.country_id
                                                                   or self.country).id)
                for expression in scope_expressions
            }
            tags = Tag.union(tags_by_expression.values())
            balances = defaultdict(float)
            if tags:
                for tag, balance in self.env['account.move.line']._read_group(
                        self._domain(date_scope) & Domain('tax_tag_ids', 'in', tags.ids),
                        ['tax_tag_ids'], ['balance:sum']):
                    balances[tag.id] = balance
            for expression, expression_tags in tags_by_expression.items():
                # a grid that receives credits is a formula with a minus: the sales print as positive figures
                sign = -1 if expression.formula.startswith('-') else 1
                self.cache[expression.id] = sign * sum(balances[tag.id] for tag in expression_tags)

    def _domain_engine(self, expression):
        domain = self._domain(expression.date_scope) & Domain(ast.literal_eval(expression.formula))
        subformula = (expression.subformula or 'sum').strip()
        if subformula == 'count_rows':
            return self.env['account.move.line'].search_count(domain)
        sign = -1 if subformula.startswith('-') else 1
        [balance] = self.env['account.move.line']._read_group(domain, [], ['balance:sum'])[0]
        value = sign * (balance or 0.0)
        if subformula.endswith('sum_if_pos'):
            return max(value, 0.0)
        if subformula.endswith('sum_if_neg'):
            return min(value, 0.0)
        return value

    def _account_codes_engine(self, expression):
        domain = self._domain(expression.date_scope)
        total = 0.0
        for sign, prefix, excluded, side in ACCOUNT_CODES_REGEX.findall(expression.formula):
            term_domain = domain & Domain('account_id.code', '=like', prefix + '%')
            for excluded_prefix in filter(None, (code.strip() for code in excluded.split(','))):
                term_domain &= Domain('account_id.code', 'not =like', excluded_prefix + '%')
            balances = [balance for _account, balance in self.env['account.move.line']._read_group(
                term_domain, ['account_id'], ['balance:sum'])]
            if side == 'D':
                balances = [balance for balance in balances if balance > 0]
            elif side == 'C':
                balances = [balance for balance in balances if balance < 0]
            total += (-1 if sign == '-' else 1) * sum(balances)
        return total

    def _external_engine(self, expression):
        # the values typed in the tax return of Enterprise; none in Community unless imported
        date_from, date_to = self._dates(expression.date_scope)
        domain = [('target_report_expression_id', '=', expression.id), ('company_id', '=', self.company.id),
                  ('date', '<=', date_to)]
        if expression.formula == 'most_recent':
            value = self.env['account.report.external.value'].search(domain, order='date desc, id desc', limit=1)
            return value.value
        if date_from:
            domain.append(('date', '>=', date_from))
        return sum(self.env['account.report.external.value'].search(domain).mapped('value'))

    # the totals ---------------------------------------------------------------------------------------------

    def _term(self, report_id, code, label):
        expression = self.by_code.get((report_id, code, label))
        return self.value(expression) if expression else 0.0

    def _aggregation_engine(self, expression):
        line = expression.report_line_id
        subformula = (expression.subformula or '').strip()
        report_id = line.report_id.id
        if subformula.startswith('cross_report'):
            target = re.match(r'cross_report\(([^,)]+)', subformula).group(1).strip()
            report_id = int(target) if target.isdigit() else self.env.ref(target).id
        if expression.formula.strip() == 'sum_children':
            return sum(self.value(child_expression) or 0.0 for child_expression in
                       line.children_ids.expression_ids.filtered(lambda e: e.label == expression.label))
        formula = TERM_REGEX.sub(
            lambda match: '(%r)' % float(self._term(report_id, match.group(1), match.group(2)) or 0.0),
            expression.formula)
        try:
            value = float(safe_eval(formula))
        except ZeroDivisionError:
            value = 0.0
        return self._apply_subformula(value, subformula, report_id)

    def _apply_subformula(self, value, subformula, report_id):
        if match := re.match(r'if_above\(%s\)' % AMOUNT_REGEX, subformula):
            return value if value > float(match.group(1)) else 0.0
        if match := re.match(r'if_below\(%s\)' % AMOUNT_REGEX, subformula):
            return value if value < float(match.group(1)) else 0.0
        if match := re.match(r'if_between\(%s,\s*%s\)' % (AMOUNT_REGEX, AMOUNT_REGEX), subformula):
            return value if float(match.group(1)) < value < float(match.group(2)) else 0.0
        if match := re.match(r'if_other_expr_(above|below)\((\w+)\.(\w+),\s*%s\)' % AMOUNT_REGEX, subformula):
            other = self._term(report_id, match.group(2), match.group(3)) or 0.0
            bound = float(match.group(4))
            return value if (other > bound if match.group(1) == 'above' else other < bound) else 0.0
        if match := re.match(r'round\((\d+)(?:,\s*(UP|DOWN|HALF-UP))?\)', subformula):
            return float_round(value, precision_digits=int(match.group(1)),
                               rounding_method=match.group(2) or 'HALF-UP')
        return value

    def value(self, expression):
        if expression.id in self.cache:
            return self.cache[expression.id]
        if expression.id in self.computing:
            # a formula that refers to itself: not a figure
            return 0.0
        self.computing.add(expression.id)
        engine = expression.engine
        if engine == 'aggregation':
            value = self._aggregation_engine(expression)
        elif engine == 'domain':
            value = self._domain_engine(expression)
        elif engine == 'account_codes':
            value = self._account_codes_engine(expression)
        elif engine == 'external':
            value = self._external_engine(expression)
        elif engine == 'text':
            value = expression.formula
        else:
            # custom: the Python of Enterprise
            value = None
        self.computing.discard(expression.id)
        self.cache[expression.id] = value
        return value
