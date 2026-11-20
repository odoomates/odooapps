from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.osv.expression import AND, OR
from odoo.addons.om_report_engine.models.report import PAGE_SIZE

# the most columns a horizontal group gives a report; the values past it are left out
MAX_HORIZONTAL_COLUMNS = 50

DETAIL_FIELDS = ['date', 'move_name', 'move_id', 'journal_id', 'partner_id', 'account_id', 'name', 'ref',
                 'matching_number', 'date_maturity', 'debit', 'credit', 'balance', 'amount_currency', 'currency_id']


class OmDynamicReport(models.AbstractModel):
    """What the accounting reports share: the filters on journal items, the
    fiscal year of the company, initial balances, the journal items behind a
    figure, and lines built as a tree of nodes.

    A node is {'id', 'name', 'line', 'children'}; the ids of the children start
    with the id of their parent and a '|', so the engine finds them. A node
    without children may still unfold: _odr_detail_lines gives its lines.

    A report declaring _report_group_by gives rows instead, and the engine
    groups them (see om.report).
    """
    _name = 'om.dynamic.report'
    _inherit = 'om.report'
    _description = 'Dynamic Accounting Report'

    _report_app = 'accounting'
    _report_group = 'account.group_account_readonly,account.group_account_manager'
    _report_default_preset = 'this_year'
    _report_rounding = True
    # the report splits its amounts in the columns of a horizontal group
    _odr_horizontal = False

    # ------------------------------------------------------------------
    # Catalog and periods
    # ------------------------------------------------------------------

    @api.model
    def _om_sections(self):
        return {
            'statements': self.env._("Statements"),
            'ledgers': self.env._("Ledgers"),
            'partners': self.env._("Partners"),
        }

    @api.model
    def _om_year_dates(self, day):
        dates = self.env.company.compute_fiscalyear_dates(day)
        return dates['date_from'], dates['date_to']

    @api.model
    def _om_date_presets(self):
        presets = super()._om_date_presets()
        labels = {
            'this_year': self.env._("This financial year"),
            'last_year': self.env._("Last financial year"),
        } if self._report_date_mode == 'range' else {
            'this_year': self.env._("End of this financial year"),
            'last_year': self.env._("End of last financial year"),
        }
        for preset in presets:
            preset['label'] = labels.get(preset['key'], preset['label'])
        return presets

    @api.model
    def _odr_fiscal_year_start(self, day):
        return self._om_year_dates(fields.Date.to_date(day))[0]

    # ------------------------------------------------------------------
    # Filters and options shared by the reports
    # ------------------------------------------------------------------

    @api.model
    def _odr_filter(self, key):
        companies = self.env.companies.ids
        filters = {
            'journal_ids': {'label': self.env._("Journals"), 'model': 'account.journal', 'icon': 'book',
                            'domain': [['company_id', 'child_of', companies]]},
            'account_ids': {'label': self.env._("Accounts"), 'model': 'account.account', 'icon': 'account_tree',
                            'domain': [['company_ids', 'parent_of', companies]]},
            'account_tag_ids': {'label': self.env._("Account Tags"), 'model': 'account.account.tag',
                                'icon': 'sell', 'domain': [['applicability', '=', 'accounts']]},
            'partner_ids': {'label': self.env._("Partners"), 'model': 'res.partner', 'icon': 'person', 'domain': []},
            'partner_category_ids': {'label': self.env._("Partner Tags"), 'model': 'res.partner.category',
                                     'icon': 'label', 'domain': []},
            'analytic_account_ids': {'label': self.env._("Analytic"), 'model': 'account.analytic.account',
                                     'icon': 'donut_small', 'domain': []},
            'aml_filter_ids': {'label': self.env._("Saved Filters"), 'model': 'ir.filters', 'icon': 'bookmark',
                               'domain': [['model_id', '=', 'account.move.line'],
                                          '|', ['user_ids', '=', False], ['user_ids', 'in', [self.env.uid]]]},
        }
        return {'key': key, **filters[key]}

    @api.model
    def _odr_filters(self, *keys):
        if 'analytic_account_ids' in keys and not self.env.user.has_group('analytic.group_analytic_accounting'):
            keys = tuple(k for k in keys if k != 'analytic_account_ids')
        return [self._odr_filter(key) for key in keys]

    @api.model
    def _odr_target_move_choice(self):
        return {'key': 'target_move', 'label': self.env._("Entries"), 'icon': 'check_circle', 'menu': 'bar',
                'default': 'posted', 'choices': [['posted', self.env._("Posted entries")],
                                                 ['all', self.env._("All entries")]]}

    # ------------------------------------------------------------------
    # Journal items
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Companies and currencies
    # ------------------------------------------------------------------

    @api.model
    def _om_default_options(self):
        return {**super()._om_default_options(), 'presentation_currency': str(self.env.company.currency_id.id)}

    @api.model
    def _om_choices_meta(self):
        choices = super()._om_choices_meta()
        currencies = self.env['res.currency'].search([('active', '=', True)], order='name')
        if len(currencies) > 1:
            choices.append({'key': 'presentation_currency', 'label': self.env._("Currency"), 'icon': 'currency_exchange',
                            'menu': 'bar', 'summary': False,
                            'choices': [[str(currency.id), currency.name] for currency in currencies]})
        return choices

    @api.model
    def _om_prepare(self, options):
        # the amounts in another currency are converted: the balances at the rates of the end of the
        # period, the flows at the average rates of their months (_odr_sums)
        currency_id = str(options.get('presentation_currency') or '')
        currency = self.env['res.currency'].browse(int(currency_id) if currency_id.isdigit() else 0).exists()
        return self.with_context(
            odr_rate_date=options.get('date_to') or fields.Date.context_today(self),
            odr_period_start=options.get('date_from') or False,
            odr_currency_id=currency.id if currency and currency.active else False)

    @api.model
    def _om_currency(self):
        currency = self.env['res.currency'].browse(self.env.context.get('odr_currency_id') or 0)
        return currency or self.env.company.currency_id

    @api.model
    def _odr_companies(self):
        """The companies of the report: those selected in the company switcher, and the branches
        they consolidate."""
        return self.env['res.company'].browse(self.env['account.move.line']._branch_ids(self.env.companies.ids))

    @api.model
    def _odr_rates_label(self, options):
        return self.env._("%(currency)s, at the rates of %(date)s", currency=self._om_currency().name,
                          date=self._om_format_date(self.env.context.get('odr_rate_date') or options.get('date_to')))

    @api.model
    def _odr_company_ids(self):
        return self._odr_companies().ids

    @api.model
    def _odr_converts(self):
        """Whether some companies of the report keep their books in another currency."""
        return bool(self._odr_companies().currency_id - self._om_currency())

    @api.model
    def _odr_convert(self, amount, company, date=None):
        """``amount``, in the currency of ``company``, in the currency of the report, at the rate of
        ``date`` (the end of the period by default: the closing rate)."""
        currency = self._om_currency()
        if not amount or company.currency_id == currency:
            return amount
        date = date or self.env.context.get('odr_rate_date') or fields.Date.context_today(self)
        return company.currency_id._convert(amount, currency, self.env.company, date, round=False)

    @api.model
    def _odr_average_factor(self, from_currency, start, end):
        """The average rate from ``from_currency`` to the currency of the report over the days from
        ``start`` to ``end``: each rate weighed by the days it applies."""
        to_currency = self._om_currency()
        if from_currency == to_currency:
            return 1.0
        start, end = fields.Date.to_date(start), fields.Date.to_date(end)
        company = self.env.company.root_id
        cache = self.env.cr.cache.setdefault('om_dynamic_reports.average_rates', {})
        key = (from_currency.id, to_currency.id, company.id, start, end)
        if key not in cache:
            # a rate applies from the day after its date: the days the rates change split the period
            changes = self.env['res.currency.rate'].sudo().search([
                ('currency_id', 'in', (from_currency | to_currency).ids), ('company_id', 'in', (False, company.id)),
                ('name', '>=', start), ('name', '<', end)])
            boundaries = sorted({start} | {day + timedelta(days=1) for day in changes.mapped('name')})
            total = 0.0
            for index, first in enumerate(boundaries):
                last = boundaries[index + 1] - timedelta(days=1) if index + 1 < len(boundaries) else end
                days = (last - first).days + 1
                total += days * self.env['res.currency']._get_conversion_rate(from_currency, to_currency, company, first)
            cache[key] = total / ((end - start).days + 1)
        return cache[key]

    @api.model
    def _odr_convert_flow(self, amount, company, month):
        """An amount of the month starting on ``month``, at the average rate of the month (of its
        days in the period)."""
        if not amount or company.currency_id == self._om_currency():
            return amount
        start = month
        end = month + relativedelta(months=1, days=-1)
        period_start = self.env.context.get('odr_period_start')
        period_end = self.env.context.get('odr_rate_date')
        if period_start:
            start = max(start, fields.Date.to_date(period_start))
        if period_end:
            end = min(end, fields.Date.to_date(period_end))
        if start > end:
            start = end
        return amount * self._odr_average_factor(company.currency_id, start, end)

    @api.model
    def _om_filter_summary(self, options):
        summary = super()._om_filter_summary(options)
        companies = self.env.companies
        if len(companies) > 1:
            summary.insert(1, (self.env._("Companies"), ', '.join(companies.mapped('name'))))
        if self._odr_converts():
            summary.insert(2 if len(companies) > 1 else 1, (self.env._("Currency"), self._odr_rates_label(options)))
        return summary

    @api.model
    def _odr_domain(self, options, date_from=False, date_to=False, before=False):
        """The journal items the options select, between two dates (both included) or ``before`` one."""
        domain = [
            ('company_id', 'in', self._odr_company_ids()),
            ('display_type', 'not in', ('line_section', 'line_subsection', 'line_note')),
            ('parent_state', '=', 'posted') if options.get('target_move', 'posted') == 'posted'
            else ('parent_state', 'in', ('draft', 'posted')),
        ]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        if before:
            domain.append(('date', '<', before))
        if options.get('journal_ids'):
            domain.append(('journal_id', 'in', options['journal_ids']))
        if options.get('account_ids'):
            domain.append(('account_id', 'in', options['account_ids']))
        if options.get('account_tag_ids'):
            domain.append(('account_id.tag_ids', 'in', options['account_tag_ids']))
        if options.get('partner_ids'):
            domain.append(('partner_id', 'in', options['partner_ids']))
        if options.get('partner_category_ids'):
            domain.append(('partner_id.category_id', 'in', options['partner_category_ids']))
        if options.get('analytic_account_ids'):
            domain.append(('analytic_distribution', 'in', options['analytic_account_ids']))
        if options.get('aml_filter_ids'):
            domain += self._odr_saved_filters_domain(options['aml_filter_ids'])
        return domain

    @api.model
    def _odr_saved_filters_domain(self, filter_ids):
        """The journal items of the saved filters chosen (the favorites of the Journal Items list): those of any
        of them."""
        saved = self.env['ir.filters'].browse(filter_ids).exists().filtered(
            lambda saved_filter: saved_filter.model_id == 'account.move.line')
        domains = []
        for saved_filter in saved:
            try:
                domains.append(saved_filter._get_eval_domain())
            except (ValueError, SyntaxError):
                continue
        return OR(domains) if domains else []

    @api.model
    def _odr_period_domain(self, options):
        """The dates of the period, as a domain; up to its end for an 'as of' report."""
        domain = [('date', '<=', options['date_to'])]
        if options.get('date_from'):
            domain.append(('date', '>=', options['date_from']))
        return domain

    @api.model
    def _odr_periods(self, options):
        """[(report, options)] of each period shown: the report with the context of its own period
        (the rates it is converted at), this period first."""
        return [(self._om_prepare(period), period) for period in self._odr_period_options(options)]

    @api.model
    def _odr_period_options(self, options):
        """The options of each period shown: this one, then the compared ones."""
        periods = [options]
        for period in self._om_compare_periods(options):
            periods.append({**options, 'date_preset': 'custom', 'date_from': period['date_from'],
                            'date_to': period['date_to'], 'compare': False})
        return periods

    @api.model
    def _odr_sums(self, domain, groupby, flow=False):
        """{group value: {'debit', 'credit', 'balance'}} of the journal items of ``domain``, in the
        currency of the report: at the closing rate, or for a ``flow`` (income, expense, the cash of
        a period) month by month at the average rate of each month."""
        return {key[0]: sums for key, sums in self._odr_grouped_sums(domain, [groupby], flow).items()}

    @api.model
    def _odr_grouped_sums(self, domain, groupbys, flow=False):
        """{(group values): {'debit', 'credit', 'balance'}}: _odr_sums by several fields at once,
        the records given by their ids (False for none)."""
        result = {}
        aggregates = ['debit:sum', 'credit:sum', 'balance:sum']
        count = len(groupbys)

        def key_of(row):
            return tuple(value.id if hasattr(value, 'id') else value for value in row[:count])

        if not self._odr_converts():
            for row in self.env['account.move.line']._read_group(domain, list(groupbys), aggregates):
                debit, credit, balance = row[-3:]
                result[key_of(row)] = {'debit': debit, 'credit': credit, 'balance': balance}
            return result
        full = list(groupbys) + ([] if 'company_id' in groupbys else ['company_id'])
        company_index = full.index('company_id')
        if flow:
            full.append('date:month')
        for row in self.env['account.move.line']._read_group(domain, full, aggregates):
            company = row[company_index]
            debit, credit, balance = row[-3:]
            if flow:
                convert = lambda amount: self._odr_convert_flow(amount, company, row[len(full) - 1])  # noqa: E731
            else:
                convert = lambda amount: self._odr_convert(amount, company)  # noqa: E731
            bucket = result.setdefault(key_of(row), {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
            bucket['debit'] += convert(debit)
            bucket['credit'] += convert(credit)
            bucket['balance'] += convert(balance)
        return result

    @api.model
    def _odr_initial_domains(self, options, domain):
        """The domains of the initial balance at the start of the period: the whole history of the
        balance sheet accounts, the income and expense since the start of the fiscal year (they start
        again at zero every year). [] without a start date."""
        date_from = options.get('date_from')
        if not date_from:
            return []
        fiscal_start = self._odr_fiscal_year_start(date_from)
        domains = [domain + [('date', '<', date_from), ('account_id.include_initial_balance', '=', True)]]
        if fiscal_start < fields.Date.to_date(date_from):
            domains.append(domain + [('date', '>=', fiscal_start), ('date', '<', date_from),
                                     ('account_id.include_initial_balance', '=', False)])
        return domains

    @api.model
    def _odr_undistributed_domain(self, options, domain):
        """The income and expense of the fiscal years before the one of the period: no account
        carries them forward, but without them the report does not balance."""
        if not options.get('date_from'):
            return False
        fiscal_start = self._odr_fiscal_year_start(options['date_from'])
        return domain + [('date', '<', fiscal_start), ('account_id.include_initial_balance', '=', False)]

    @api.model
    def _odr_add(self, target, sums):
        for key, values in sums.items():
            bucket = target.setdefault(key, {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
            for field in ('debit', 'credit', 'balance'):
                bucket[field] += values[field]
        return target

    @api.model
    def _odr_label(self, line):
        """The label of a journal item: its entry, reference and label, each said once."""
        parts = []
        for value in (line.ref, line.name):
            value = (value or '').strip()
            if value in ('', '/') or value == line.move_name or any(value in kept for kept in parts):
                continue
            parts = [kept for kept in parts if kept not in value]
            parts.append(value)
        return ' - '.join(parts)

    @api.model
    def _odr_detail_values(self, line, running):
        company_currency = line.company_currency_id
        foreign = line.currency_id and line.currency_id != company_currency
        return {
            'date': fields.Date.to_string(line.date),
            'move': line.move_name,
            'journal': line.journal_id.code,
            'partner': line.partner_id.display_name or '',
            'account': self._odr_account_code(line.account_id) or line.account_id.display_name,
            'label': self._odr_label(line),
            'date_maturity': line.date_maturity and fields.Date.to_string(line.date_maturity),
            'matching': line.matching_number or '',
            'debit': self._odr_convert(line.debit, line.company_id),
            'credit': self._odr_convert(line.credit, line.company_id),
            'balance': running,
            'amount_currency': line.amount_currency if foreign else False,
            'currency': line.currency_id.name if foreign else '',
        }

    @api.model
    def _odr_item_lines(self, parent, domain, opening, order, offset, limit, opening_label=False):
        """The journal items of ``domain`` under ``parent``, with a running balance from ``opening``
        ({'debit', 'credit', 'balance'} or False for none); the opening line comes first."""
        MoveLine = self.env['account.move.line']
        lines = []
        has_opening = bool(opening)
        start = offset
        if has_opening:
            if offset == 0:
                lines.append(self._om_line(
                    '%s|opening' % parent['id'], opening_label or self.env._("Initial Balance"),
                    {'debit': opening['debit'], 'credit': opening['credit'], 'balance': opening['balance']},
                    parent_id=parent['id'], level=parent['level'] + 1, kind='opening'))
                if limit:
                    limit -= 1
            else:
                start -= 1
        count = MoveLine.search_count(domain)
        running = opening['balance'] if has_opening else 0.0
        if start:
            running += sum(self._odr_convert(line.balance, line.company_id) for line in MoveLine.search_fetch(
                domain, ['balance', 'company_id'], order=order, limit=start))
        items = MoveLine.search_fetch(domain, DETAIL_FIELDS + ['company_id'], order=order, offset=start,
                                      limit=limit or None)
        currency = self._om_currency()
        for item in items:
            running = currency.round(running + self._odr_convert(item.balance, item.company_id))
            lines.append(self._om_line(
                '%s|aml-%s' % (parent['id'], item.id), item.move_name or '', self._odr_detail_values(item, running),
                parent_id=parent['id'], level=parent['level'] + 1, kind='detail',
                open_record=('account.move', item.move_id.id)))
        return lines, max(count - start - len(items), 0)

    @api.model
    def _odr_cell_scope(self, options, column_key):
        """(key without its period, options of the period) of a column: 'end_debit_1' is the
        ending debit of the first period compared with."""
        periods = self._odr_period_options(options)
        base, _sep, index = column_key.rpartition('_')
        if base and index.isdigit() and 0 < int(index) < len(periods):
            return base, periods[int(index)]
        return column_key, options

    @api.model
    def _om_note_scope(self, options, column_key):
        # a note on a compared column is a note on the figure of that period
        key, period = self._odr_cell_scope(options, column_key)
        return key, period.get('date_from') or False, period.get('date_to') or False

    @api.model
    def _odr_analytic_cell_action(self, options, column_key, account, date_domain, name):
        """The analytic lines of an analytic column for an account: the share of each journal item
        its distribution gives the column."""
        columns = {'an_%s' % key: domain for key, _label, domain in self._odr_analytic_columns(options)}
        if column_key not in columns:
            return False
        domain = [('company_id', 'in', self._odr_company_ids()), ('general_account_id', '=', account.id)]
        domain += date_domain + columns[column_key]
        if options.get('journal_ids'):
            domain.append(('journal_id', 'in', options['journal_ids']))
        action = self.env['ir.actions.act_window']._for_xml_id('analytic.account_analytic_line_action_entries')
        action.update({'name': name, 'domain': domain, 'context': {'create': False}, 'target': 'current'})
        action.pop('path', None)
        return action

    @api.model
    def _odr_open_domain(self, date):
        """The journal items still open at ``date``: not reconciled yet, or reconciled after it."""
        return ['|', '|', ('reconciled', '=', False), ('matched_debit_ids.max_date', '>', date),
                ('matched_credit_ids.max_date', '>', date)]

    @api.model
    def _odr_open_amounts(self, lines, date):
        """{line id: what is open at ``date``}: its balance less what was matched with it up to the
        date, in the currency of the report."""
        if not lines:
            return {}
        Partial = self.env['account.partial.reconcile']
        matched = {}
        for side, sign in (('credit_move_id', 1), ('debit_move_id', -1)):
            for line, amount in Partial._read_group(
                    [(side, 'in', lines.ids), ('max_date', '<=', date)], [side], ['amount:sum']):
                matched[line.id] = matched.get(line.id, 0.0) + sign * amount
        return {line.id: self._odr_convert(line.balance + matched.get(line.id, 0.0), line.company_id)
                for line in lines}

    @api.model
    def _odr_journal_items_action(self, domain, name):
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_moves_all')
        action.update({
            'name': name,
            'domain': domain,
            'context': {'create': False, 'search_default_group_by_move': 0},
            'target': 'current',
        })
        action.pop('path', None)
        return action

    # ------------------------------------------------------------------
    # Analytic columns
    # ------------------------------------------------------------------

    @api.model
    def _odr_analytic_column_filters(self):
        """The pickers of the analytic columns, with analytic accounting only."""
        if not self.env.user.has_group('analytic.group_analytic_accounting'):
            return []
        return [
            {'key': 'analytic_column_ids', 'label': self.env._("Analytic Columns"),
             'model': 'account.analytic.account', 'icon': 'view_column', 'domain': []},
            {'key': 'analytic_plan_column_ids', 'label': self.env._("Plan Columns"),
             'model': 'account.analytic.plan', 'icon': 'view_week', 'domain': [['parent_id', '=', False]]},
        ]

    @api.model
    def _odr_analytic_columns(self, options):
        """[(key, label, domain on the analytic lines)] of the analytic columns asked for."""
        columns = []
        for account in self.env['account.analytic.account'].browse(options.get('analytic_column_ids') or []).exists():
            columns.append(('a%s' % account.id, account.display_name,
                            [(account.plan_id._column_name(), '=', account.id)]))
        for plan in self.env['account.analytic.plan'].browse(options.get('analytic_plan_column_ids') or []).exists():
            columns.append(('p%s' % plan.id, plan.name, [(plan._column_name(), '!=', False)]))
        return columns

    @api.model
    def _odr_analytic_sums(self, options, column_domain, date_domain, flow=False):
        """{account id: {'debit', 'credit', 'balance'}} of the analytic lines of a column: the share
        of each journal item that its analytic distribution gives the column. The analytic lines
        are those of the posted entries."""
        domain = [('company_id', 'in', self._odr_company_ids()), ('general_account_id', '!=', False)]
        domain += date_domain + column_domain
        if options.get('journal_ids'):
            domain.append(('journal_id', 'in', options['journal_ids']))
        result = {}
        groupbys = ['general_account_id', 'company_id'] + (['date:month'] if flow else [])
        for row in self.env['account.analytic.line']._read_group(domain, groupbys, ['amount:sum']):
            account, company, amount = row[0], row[1], row[-1]
            bucket = result.setdefault(account.id, {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
            bucket['balance'] -= (self._odr_convert_flow(amount, company, row[2]) if flow
                                  else self._odr_convert(amount, company))
        return result

    # ------------------------------------------------------------------
    # Horizontal groups
    # ------------------------------------------------------------------

    @api.model
    def _odr_horizontal_groups(self):
        """The horizontal groups the report offers."""
        groups = self.env['om.report.horizontal.group'].sudo().search(
            [('company_id', 'in', [False] + self.env.companies.ids), ('rule_ids', '!=', False)])
        return groups.filtered(lambda group: group._odr_applies_to(self._name))

    @api.model
    def _odr_horizontal_choice(self):
        """The dropdown of the horizontal groups, in a list: [] without any."""
        groups = self._odr_horizontal_groups() if self._odr_horizontal else []
        if not groups:
            return []
        return [{'key': 'horizontal_group', 'label': self.env._("Horizontal Group"), 'icon': 'view_column',
                 'menu': 'bar', 'default': 'none',
                 'choices': [['none', self.env._("No horizontal group")]]
                 + [[str(group.id), group.name] for group in groups]}]

    @api.model
    def _odr_horizontal_group(self, options):
        """The horizontal group the report is split by, or an empty recordset."""
        value = str(options.get('horizontal_group') or '')
        if not self._odr_horizontal or not value.isdigit():
            return self.env['om.report.horizontal.group']
        group = self.env['om.report.horizontal.group'].sudo().browse(int(value)).exists()
        return group if group and group.rule_ids and group._odr_applies_to(self._name) else group.browse()

    @api.model
    def _om_clean_options(self, options):
        options = super()._om_clean_options(options)
        if self._odr_horizontal_group(options):
            # one kind of split columns at a time: the horizontal group wins over the analytic columns
            options.update(analytic_column_ids=[], analytic_plan_column_ids=[])
        return options

    @api.model
    def _odr_horizontal_fields(self, group):
        """The journal item fields of the rules of ``group``, in order."""
        AccountMoveLine = self.env['account.move.line']
        return [rule for rule in group.rule_ids if rule.field_id.name in AccountMoveLine._fields]

    @api.model
    def _odr_horizontal_scope(self, options):
        """The journal items the values of the columns are taken from: those of every period shown."""
        periods = self._odr_period_options(options)
        domain = self._odr_domain(options) + [('date', '<=', max(period['date_to'] for period in periods))]
        starts = [period.get('date_from') for period in periods]
        if self._report_date_mode != 'as_of' and all(starts):
            domain.append(('date', '>=', min(starts)))
        return domain

    @api.model
    def _odr_horizontal_key(self, values):
        # no '_' and no plain number after the last one: _odr_cell_scope reads that as the period
        return 'hg_' + '-'.join('v%s' % (value or 0) for value in values)

    @api.model
    def _odr_horizontal_layout(self, options):
        """([{'key', 'label', 'values', 'domain'}], truncated) of the columns of the horizontal group:
        one per combination of values found in the journal items of the report, the values of each
        rule kept by its domain and in the order of their model."""
        group = self._odr_horizontal_group(options)
        rules = self._odr_horizontal_fields(group)
        if not rules:
            return [], False
        cache = self.env.cr.cache.setdefault('om_dynamic_reports.horizontal_layout', {})
        cache_key = (self._name, self.env.uid, tuple(self.env.companies.ids), self.env.lang, group.id,
                     str(group.write_date), str(max(rules, key=lambda r: r.write_date).write_date),
                     repr(sorted((key, str(value)) for key, value in options.items())))
        if cache_key in cache:
            return cache[cache_key]
        names = [rule.field_id.name for rule in rules]
        combinations = [tuple(value.id for value in row[:len(names)]) for row in
                        self.env['account.move.line']._read_group(self._odr_horizontal_scope(options), names)]
        orders, labels = [], {}
        for index, rule in enumerate(rules):
            Model = self.env[rule.field_id.relation].with_context(active_test=False)
            ids = {combination[index] for combination in combinations if combination[index]}
            kept = Model.search(AND([[('id', 'in', list(ids))], rule._odr_domain()])) if ids else Model
            order = {record.id: position for position, record in enumerate(kept)}
            if rule.domain in (False, '', '[]'):
                # the journal items without a value get a column of their own, so the columns add up
                order[False] = len(order)
                labels[(index, False)] = self.env._("No %s", rule.field_id.field_description)
            shown = [record.display_name for record in kept]
            for record in kept:
                label = record.display_name
                if shown.count(label) > 1 and 'company_id' in record._fields and record.company_id:
                    # the same name in several companies, such as their Sales journals
                    label = '%s (%s)' % (label, record.company_id.name)
                labels[(index, record.id)] = label
            orders.append(order)
        combinations = sorted(
            (combination for combination in combinations
             if all(value in order for value, order in zip(combination, orders))),
            key=lambda combination: [order[value] for value, order in zip(combination, orders)])
        truncated = len(combinations) > MAX_HORIZONTAL_COLUMNS
        columns = [{
            'key': self._odr_horizontal_key(combination),
            'label': ' / '.join(labels[(index, value)] for index, value in enumerate(combination)),
            'values': combination,
            'domain': [(name, '=', value) for name, value in zip(names, combination)],
        } for combination in combinations[:MAX_HORIZONTAL_COLUMNS]]
        cache[cache_key] = (columns, truncated)
        return columns, truncated

    @api.model
    def _odr_horizontal_columns(self, options):
        """[(key, label, domain on the journal items)] of the columns of the horizontal group."""
        return [(column['key'], column['label'], column['domain'])
                for column in self._odr_horizontal_layout(options)[0]]

    @api.model
    def _odr_horizontal_names(self, options):
        """The journal item fields the amounts are grouped by besides the account."""
        return [rule.field_id.name for rule in self._odr_horizontal_fields(self._odr_horizontal_group(options))]

    @api.model
    def _odr_horizontal_split(self, options, grouped):
        """{column key: {account id: sums}} of sums grouped by account and the fields of the group."""
        keys = {column['values']: column['key'] for column in self._odr_horizontal_layout(options)[0]}
        result = {key: {} for key in keys.values()}
        for (account_id, *values), sums in grouped.items():
            key = keys.get(tuple(values))
            if key:
                self._odr_add(result[key], {account_id: sums})
        return result

    @api.model
    def _odr_horizontal_cell_domain(self, options, column_key):
        """The domain of the journal items of a column of the horizontal group, or False."""
        domains = {key: domain for key, _label, domain in self._odr_horizontal_columns(options)}
        return domains.get(column_key, False)

    @api.model
    def _odr_split_columns(self, options):
        """[(key, label)] of the columns the amounts of a period are split in: those of the
        horizontal group, or the analytic columns."""
        if self._odr_horizontal_group(options):
            return [(key, label) for key, label, _domain in self._odr_horizontal_columns(options)]
        return [('an_%s' % key, label) for key, label, _domain in self._odr_analytic_columns(options)]

    @api.model
    def _odr_split_total_help(self, options):
        if self._odr_horizontal_group(options):
            return self.env._("Every entry of the period, whatever its column.")
        return self.env._("Every entry of the period, with or without analytic.")

    @api.model
    def _om_subtitle(self, options):
        subtitle = super()._om_subtitle(options)
        if self._odr_horizontal_group(options) and self._odr_horizontal_layout(options)[1]:
            note = self.env._("first %s columns of the horizontal group", MAX_HORIZONTAL_COLUMNS)
            subtitle = '%s (%s)' % (subtitle, note) if subtitle else note
        return subtitle

    # ------------------------------------------------------------------
    # Account hierarchy
    # ------------------------------------------------------------------

    @api.model
    def _odr_hierarchy_choice(self, with_type=True):
        choices = [('none', self.env._("No grouping"))]
        if with_type:
            choices.append(('type', self.env._("Account type")))
        choices.append(('code', self.env._("Account code")))
        return {'key': 'hierarchy', 'label': self.env._("Group accounts by"), 'default': 'none',
                'choices': choices}

    @api.model
    def _odr_account_path(self, account, hierarchy):
        """The groups above an account, from the top: [(key, name, sort key)]."""
        if hierarchy == 'type':
            Account = self.env['account.account']
            groups = Account._fields['internal_group']._description_selection(self.env)
            types = Account._fields['account_type']._description_selection(self.env)
            group = account.internal_group or 'off'
            group_index = next((i for i, (key, _l) in enumerate(groups) if key == group), 99)
            type_index = next((i for i, (key, _l) in enumerate(types) if key == account.account_type), 99)
            return [('group-%s' % group, dict(groups).get(group, group), group_index),
                    ('type-%s' % account.account_type, dict(types).get(account.account_type, ''), type_index)]
        if hierarchy == 'code':
            code = self._odr_account_code(account)
            return [('code-%s' % code[:size], code[:size], code[:size]) for size in (1, 2) if len(code) > size]
        return []

    @api.model
    def _odr_account_code(self, account):
        """The code of an account: it depends on the company, read in one of its own when the
        company of the report gives it none (an account of another company of the report)."""
        code = account.code
        if not code and account.company_ids:
            companies = account.company_ids & self._odr_companies() or account.company_ids
            code = account.with_company(companies[:1]).code
        return code or ''

    @api.model
    def _odr_account_name(self, account):
        code = self._odr_account_code(account)
        name = '%s %s' % (code, account.name) if code else account.name
        if len(self.env.companies) > 1 and account.company_ids and self.env.company not in account.company_ids:
            # with several companies, the accounts of the others say whose they are
            name = '%s (%s)' % (name, ', '.join((account.company_ids & self.env.companies).mapped('name')
                                                or account.company_ids.mapped('name')))
        return name

    @api.model
    def _odr_account_sort(self, account):
        return (self._odr_account_code(account), account.name or '')

    @api.model
    def _odr_group_accounts(self, entries, options, make_leaf, sum_keys):
        """The nodes of the accounts, grouped as options['hierarchy'] says.

        ``entries``: [(account, values)] in the order of the report; ``make_leaf(account, values,
        parent_id, level)`` gives the node of an account; the groups sum the ``sum_keys`` of their
        accounts. Without grouping, the account nodes as they come.
        """
        hierarchy = options.get('hierarchy', 'none')
        if hierarchy == 'none':
            return [make_leaf(account, values, False, 0) for account, values in entries]
        root = {'children': {}, 'leaves': []}
        for account, values in entries:
            node = root
            for key, name, sort in self._odr_account_path(account, hierarchy):
                node = node['children'].setdefault(key, {'name': name, 'sort': sort, 'children': {}, 'leaves': [],
                                                         'values': dict.fromkeys(sum_keys, 0.0)})
                for value_key in sum_keys:
                    node['values'][value_key] += values.get(value_key) or 0.0
            node['leaves'].append((account, values))

        def build(group, parent_id, level):
            # the own entries of a group first, then its sub-groups
            nodes = [make_leaf(account, values, parent_id, level) for account, values in group['leaves']]
            for key in sorted(group['children'], key=lambda k: (group['children'][k]['sort'], k)):
                child = group['children'][key]
                node_id = '%s|%s' % (parent_id, key) if parent_id else key
                children = build(child, node_id, level + 1)
                line = self._om_line(node_id, child['name'], child['values'], parent_id=parent_id, level=level,
                                     kind='group', has_children=bool(children), count=len(children))
                nodes.append(self._odr_node(node_id, child['name'], line, children))
            return nodes

        return build(root, False, 0)

    # ------------------------------------------------------------------
    # Lines from nodes
    # ------------------------------------------------------------------

    @api.model
    def _odr_node(self, node_id, name, line, children=None):
        return {'id': node_id, 'name': name, 'line': line, 'children': children or []}

    @api.model
    def _om_lines(self, data, options, parent_id=False, offset=0, limit=PAGE_SIZE):
        if self._report_group_by:
            return super()._om_lines(data, options, parent_id, offset, limit)
        if not parent_id:
            nodes = data['tree']
        else:
            node = self._om_find_node(data['tree'], parent_id)
            if not node:
                return [], 0
            if not node['children']:
                if node['line']['has_children']:
                    return self._odr_detail_lines(data, options, node['line'], offset, limit)
                return [], 0
            nodes = node['children']
        page, more = self._om_page(nodes, offset, limit)
        return [node['line'] for node in page], more

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        return [], 0

    @api.model
    def _om_compute(self, options):
        if self._report_group_by:
            return super()._om_compute(options)
        tree, total = self._odr_tree(options)
        if options['search']:
            tree = self._om_search_tree(tree, options['search'])
        return {'tree': tree, 'total': total}

    @api.model
    def _odr_tree(self, options):
        """(nodes, total values or False)."""
        return [], False

    @api.model
    def _om_total(self, data, options):
        if self._report_group_by:
            return super()._om_total(data, options)
        if not data.get('total'):
            return False
        return self._om_line('total', self.env._("Total"), data['total'], kind='total')

    @api.model
    def _odr_line_id_part(self, line_id, prefix):
        """The id of the '<prefix>-<id>' part of a line id, or False."""
        for part in reversed((line_id or '').split('|')):
            key, _sep, value = part.rpartition('-')
            if key == prefix and value.isdigit():
                return int(value)
        return False

    @api.model
    def _odr_period_label(self, options):
        return self._om_period_label(options) or self.env._("Period")

    @api.model
    def _odr_day_before(self, day):
        return fields.Date.to_string(fields.Date.to_date(day) - timedelta(days=1))
