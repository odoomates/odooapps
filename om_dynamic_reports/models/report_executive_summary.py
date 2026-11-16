from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

INCOME = ('income',)
OTHER_INCOME = ('income_other',)
COST_OF_REVENUE = ('expense_direct_cost',)
OPERATING_EXPENSES = ('expense', 'expense_depreciation')
OTHER_EXPENSES = ('expense_other',)
CASH = ('asset_cash',)
RECEIVABLE = ('asset_receivable',)
PAYABLE = ('liability_payable',)
CURRENT_ASSETS = ('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments')
CURRENT_LIABILITIES = ('liability_payable', 'liability_current', 'liability_credit_card')
ASSETS = CURRENT_ASSETS + ('asset_fixed', 'asset_non_current')
LIABILITIES = CURRENT_LIABILITIES + ('liability_non_current',)


class OmDynamicReportExecutiveSummary(models.AbstractModel):
    """Executive Summary: the key figures of the company on one page.

    Profitability and cash are the flows of the period; the balance sheet
    figures are the balances at its end; the ratios come from both. Every
    figure is a sum of journal items by account type, the same the Profit and
    Loss, the Balance Sheet and the Cash Flow add up, so they agree.
    """
    _name = 'om.dynamic.report.executive.summary'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Executive Summary'

    _report_name = 'Executive Summary'
    _report_description = _lt("Profitability, cash, balance sheet and ratios on one page.")
    _report_section = 'statements'
    _report_sequence = 0
    _report_icon = 'dashboard'
    _report_compare = True

    @api.model
    def _om_report_title(self):
        return self.env._("Executive Summary")

    @api.model
    def _om_name_label(self, options):
        return ''

    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids', 'analytic_account_ids')

    @api.model
    def _om_choices(self):
        return [self._odr_target_move_choice()]

    @api.model
    def _om_get_columns(self, options):
        periods = self._odr_period_options(options)
        columns = []
        for index, period in enumerate(periods):
            suffix = '_%s' % index if index else ''
            columns.append({'key': 'value' + suffix, 'label': self._om_period_label(period), 'type': 'monetary',
                            'optional': False, 'drill': True})
        if len(periods) == 2:
            columns.append({'key': 'variation', 'label': self.env._("Variation %"), 'type': 'percent',
                            'help': self.env._("Change from the compared period to this one, for the amounts.")})
        return columns

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_rates_label(self, options):
        return self.env._(
            "%(currency)s: balances at the rates of %(date)s, income, expenses and cash flows at the average "
            "rates of their months", currency=self._om_currency().name,
            date=self._om_format_date(self.env.context.get('odr_rate_date') or options.get('date_to')))

    @api.model
    def _odr_by_type(self, sums):
        """{account type: {'debit', 'credit', 'balance'}} from sums by account."""
        result = {}
        accounts = self.env['account.account'].with_context(active_test=False).browse(list(sums))
        for account in accounts:
            bucket = result.setdefault(account.account_type, {'debit': 0.0, 'credit': 0.0, 'balance': 0.0})
            for key in bucket:
                bucket[key] += sums[account.id][key]
        return result

    @api.model
    def _odr_figures(self, options):
        """{figure key: value} of one period."""
        domain = self._odr_domain(options)
        flows = self._odr_by_type(self._odr_sums(domain + self._odr_period_domain(options), 'account_id', flow=True))
        balances = self._odr_by_type(self._odr_sums(domain + [('date', '<=', options['date_to'])], 'account_id'))

        def flow(types, key='balance'):
            return sum(flows.get(account_type, {}).get(key, 0.0) for account_type in types)

        def balance(types):
            return sum(balances.get(account_type, {}).get('balance', 0.0) for account_type in types)

        def ratio(numerator, denominator):
            return numerator / denominator if denominator else False

        figures = {
            'revenue': -flow(INCOME),
            'cost_of_revenue': flow(COST_OF_REVENUE),
            'operating_expenses': flow(OPERATING_EXPENSES),
            'other_income': -flow(OTHER_INCOME),
            'other_expenses': flow(OTHER_EXPENSES),
            'cash_received': flow(CASH, 'debit'),
            'cash_spent': flow(CASH, 'credit'),
            'cash_closing': balance(CASH),
            'receivables': balance(RECEIVABLE),
            'payables': -balance(PAYABLE),
            'current_assets': balance(CURRENT_ASSETS),
            'current_liabilities': -balance(CURRENT_LIABILITIES),
            'total_assets': balance(ASSETS),
            'total_liabilities': -balance(LIABILITIES),
        }
        figures['gross_profit'] = figures['revenue'] - figures['cost_of_revenue']
        figures['operating_profit'] = figures['gross_profit'] - figures['operating_expenses']
        figures['net_profit'] = figures['operating_profit'] + figures['other_income'] - figures['other_expenses']
        figures['cash_surplus'] = figures['cash_received'] - figures['cash_spent']
        figures['working_capital'] = figures['current_assets'] - figures['current_liabilities']
        figures['net_assets'] = figures['total_assets'] - figures['total_liabilities']
        days = (fields.Date.to_date(options['date_to']) - fields.Date.to_date(options['date_from'])).days + 1
        revenue = figures['revenue']
        figures.update({
            'gross_margin': ratio(figures['gross_profit'] * 100, revenue),
            'operating_margin': ratio(figures['operating_profit'] * 100, revenue),
            'net_margin': ratio(figures['net_profit'] * 100, revenue),
            'current_ratio': ratio(figures['current_assets'], figures['current_liabilities']),
            'quick_ratio': ratio(figures['cash_closing'] + figures['receivables'], figures['current_liabilities']),
            'dso': ratio(figures['receivables'] * days, revenue),
            'dpo': ratio(figures['payables'] * days, figures['cost_of_revenue'] + figures['operating_expenses']),
            'return_on_assets': ratio(figures['net_profit'] * 100, figures['total_assets']),
        })
        return figures

    @api.model
    def _odr_layout(self):
        """[(section key, section label, [(figure key, label, type, help)])]."""
        _ = self.env._
        return [
            ('profitability', _("Profitability"), [
                ['revenue', _("Revenue"), 'monetary', ''],
                ['cost_of_revenue', _("Cost of Revenue"), 'monetary', ''],
                ['gross_profit', _("Gross Profit"), 'monetary', _("Revenue less the cost of revenue.")],
                ['operating_expenses', _("Operating Expenses"), 'monetary', _("Expenses and depreciation.")],
                ['operating_profit', _("Operating Profit"), 'monetary', ''],
                ['other_income', _("Other Income"), 'monetary', ''],
                ['other_expenses', _("Other Expenses"), 'monetary', ''],
                ['net_profit', _("Net Profit"), 'monetary', ''],
                ['gross_margin', _("Gross Margin"), 'percent', _("Gross profit / revenue.")],
                ['operating_margin', _("Operating Margin"), 'percent', _("Operating profit / revenue.")],
                ['net_margin', _("Net Margin"), 'percent', _("Net profit / revenue.")],
            ]),
            ['cash', _("Cash"), [
                ['cash_received', _("Cash Received"), 'monetary', ''],
                ['cash_spent', _("Cash Spent"), 'monetary', ''],
                ['cash_surplus', _("Cash Surplus"), 'monetary', _("Cash received less cash spent.")],
                ['cash_closing', _("Closing Bank and Cash Balance"), 'monetary', ''],
            ]],
            ['balance_sheet', _("Balance Sheet"), [
                ['receivables', _("Receivables"), 'monetary', ''],
                ['payables', _("Payables"), 'monetary', ''],
                ['current_assets', _("Current Assets"), 'monetary', ''],
                ['current_liabilities', _("Current Liabilities"), 'monetary', ''],
                ['working_capital', _("Net Working Capital"), 'monetary',
                 _("Current assets less current liabilities.")],
                ['total_assets', _("Total Assets"), 'monetary', ''],
                ['total_liabilities', _("Total Liabilities"), 'monetary', ''],
                ['net_assets', _("Net Assets"), 'monetary', _("Total assets less total liabilities: the equity.")],
            ]],
            ['ratios', _("Ratios"), [
                ['current_ratio', _("Current Ratio"), 'ratio', _("Current assets / current liabilities.")],
                ['quick_ratio', _("Quick Ratio"), 'ratio', _("Cash and receivables / current liabilities.")],
                ['dso', _("Days Sales Outstanding"), 'days', _("Receivables / revenue, in days of the period.")],
                ['dpo', _("Days Payable Outstanding"), 'days',
                 _("Payables / cost of revenue and expenses, in days of the period.")],
                ['return_on_assets', _("Return on Assets"), 'percent', _("Net profit / total assets.")],
            ]],
        ]

    @api.model
    def _odr_tree(self, options):
        periods = self._odr_period_options(options)
        figures = [report._odr_figures(period) for report, period in self._odr_periods(options)]
        suffixes = ['_%s' % index if index else '' for index in range(len(periods))]
        nodes = []
        for section, section_label, rows in self._odr_layout():
            section_id = 'section-%s' % section
            children = []
            for key, label, kind, help_text in rows:
                values = {'value' + suffix: period_figures[key] for suffix, period_figures in zip(suffixes, figures)}
                if len(periods) == 2 and kind == 'monetary':
                    current, previous = values['value'], values['value_1']
                    values['variation'] = (current - previous) / abs(previous) * 100 if previous else False
                line_id = '%s|figure-%s' % (section_id, key)
                children.append(self._odr_node(line_id, label, self._om_line(
                    line_id, label, values, parent_id=section_id, level=1, kind='leaf',
                    drill=key in self._odr_drill_types(), help=help_text,
                    types={'value' + suffix: kind for suffix in suffixes} if kind != 'monetary' else {})))
            nodes.append(self._odr_node(section_id, section_label, self._om_line(
                section_id, section_label, {}, kind='group', has_children=True, count=len(children),
                unfolded=True), children))
        return nodes, False

    # ------------------------------------------------------------------
    # Drill-down
    # ------------------------------------------------------------------

    @api.model
    def _odr_drill_types(self):
        """{figure key: (account types, 'flow' or 'balance')} of the figures made of journal items."""
        return {
            'revenue': (INCOME, 'flow'),
            'cost_of_revenue': (COST_OF_REVENUE, 'flow'),
            'gross_profit': (INCOME + COST_OF_REVENUE, 'flow'),
            'operating_expenses': (OPERATING_EXPENSES, 'flow'),
            'operating_profit': (INCOME + COST_OF_REVENUE + OPERATING_EXPENSES, 'flow'),
            'other_income': (OTHER_INCOME, 'flow'),
            'other_expenses': (OTHER_EXPENSES, 'flow'),
            'net_profit': (INCOME + OTHER_INCOME + COST_OF_REVENUE + OPERATING_EXPENSES + OTHER_EXPENSES, 'flow'),
            'cash_received': (CASH, 'flow'),
            'cash_spent': (CASH, 'flow'),
            'cash_surplus': (CASH, 'flow'),
            'cash_closing': (CASH, 'balance'),
            'receivables': (RECEIVABLE, 'balance'),
            'payables': (PAYABLE, 'balance'),
            'current_assets': (CURRENT_ASSETS, 'balance'),
            'current_liabilities': (CURRENT_LIABILITIES, 'balance'),
            'working_capital': (CURRENT_ASSETS + CURRENT_LIABILITIES, 'balance'),
            'total_assets': (ASSETS, 'balance'),
            'total_liabilities': (LIABILITIES, 'balance'),
            'net_assets': (ASSETS + LIABILITIES, 'balance'),
        }

    @api.model
    def _odr_figure_action(self, period, line_id, name):
        key = (line_id or '').rpartition('figure-')[2]
        spec = self._odr_drill_types().get(key)
        if not spec:
            return False
        types, scope = spec
        dates = self._odr_period_domain(period) if scope == 'flow' else [('date', '<=', period['date_to'])]
        domain = self._odr_domain(period) + dates + [('account_id.account_type', 'in', list(types))]
        if key == 'cash_received':
            domain.append(('debit', '>', 0))
        elif key == 'cash_spent':
            domain.append(('credit', '>', 0))
        return self._odr_journal_items_action(domain, name)

    @api.model
    def _om_line_action(self, options, line_id):
        return self._odr_figure_action(options, line_id, self._om_report_title())

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        _key, period = self._odr_cell_scope(options, column_key)
        return self._odr_figure_action(period, line_id, '%s - %s' % (
            self._om_report_title(), self._om_period_label(period)))
