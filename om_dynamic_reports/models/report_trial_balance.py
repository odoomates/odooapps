from odoo import api, models
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

EMPTY = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
AMOUNTS = ('init_debit', 'init_credit', 'init_balance', 'debit', 'credit', 'balance',
           'end_debit', 'end_credit', 'end_balance')


class OmDynamicReportTrialBalance(models.AbstractModel):
    """Trial Balance: per account, the balance at the start of the period, the
    debit and credit of the period, and the balance at its end. The opening and
    closing balances are split in debit and credit, so that each pair of
    columns adds up to the same total."""
    _name = 'om.dynamic.report.trial.balance'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Trial Balance'

    _report_name = 'Trial Balance'
    _report_description = _lt("Opening balance, movements and closing balance of every account.")
    _report_section = 'statements'
    _report_sequence = 10
    _report_icon = 'balance'
    _report_compare = True

    @api.model
    def _om_report_title(self):
        return self.env._("Trial Balance")

    @api.model
    def _om_name_label(self, options):
        return self.env._("Account")

    @api.model
    def _om_filters(self):
        return (self._odr_filters('journal_ids', 'account_ids', 'account_tag_ids', 'analytic_account_ids')
                + self._odr_analytic_column_filters())

    @api.model
    def _om_choices(self):
        return [
            self._odr_target_move_choice(),
            {'key': 'display_account', 'label': self.env._("Accounts"), 'default': 'movement', 'choices': [
                ['movement', self.env._("With balance or movements")],
                ['not_zero', self.env._("With closing balance not zero")],
                ['all', self.env._("All accounts")],
            ]},
            self._odr_hierarchy_choice(),
        ]

    @api.model
    def _om_get_columns(self, options):
        columns = []
        periods = self._odr_period_options(options)
        compared = len(periods) > 1
        analytic = self._odr_analytic_columns(options)
        for index, period in enumerate(periods):
            suffix = '_%s' % index if index else ''
            if compared:
                start = period['date_from'] and self._om_format_date(period['date_from'])
                initial = self.env._("Balance at %s", start) if start else self.env._("Initial Balance")
                ending = self.env._("Balance at %s", self._om_format_date(period['date_to']))
            else:
                initial, ending = self.env._("Initial Balance"), self.env._("Ending Balance")
            movements = self._odr_period_label(period)
            for group, keys in ((initial, ('init_debit', 'init_credit', 'init_balance')),
                                (movements, ('debit', 'credit', 'balance')),
                                (ending, ('end_debit', 'end_credit', 'end_balance'))):
                for key, label in zip(keys, (self.env._("Debit"), self.env._("Credit"), self.env._("Balance"))):
                    columns.append({'key': key + suffix, 'label': label, 'type': 'monetary', 'group': group,
                                    'visible': not key.endswith('balance'), 'drill': True})
                if group == movements:
                    # the movements of the period of each analytic column, under the same header
                    for key, label, _domain in analytic:
                        columns.append({'key': 'an_%s%s' % (key, suffix), 'label': label, 'type': 'monetary',
                                        'group': group, 'drill': True})
        return columns

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_values(self, initial, period, suffix=''):
        """The columns of a line from its initial and period sums."""
        init_balance = initial['balance']
        end_balance = init_balance + period['balance']
        values = {
            'init_debit': max(init_balance, 0.0), 'init_credit': max(-init_balance, 0.0), 'init_balance': init_balance,
            'debit': period['debit'], 'credit': period['credit'], 'balance': period['balance'],
            'end_debit': max(end_balance, 0.0), 'end_credit': max(-end_balance, 0.0), 'end_balance': end_balance,
        }
        return {key + suffix: value for key, value in values.items()}

    @api.model
    def _odr_period_analytic(self, options):
        """{column key: {account id: balance}} of the analytic columns over one period."""
        return {key: {account_id: sums['balance'] for account_id, sums in self._odr_analytic_sums(
            options, domain, self._odr_period_domain(options)).items()}
            for key, _label, domain in self._odr_analytic_columns(options)}

    @api.model
    def _odr_period_figures(self, options):
        """({account id: (initial sums, period sums)}, undistributed balance) of one period."""
        domain = self._odr_domain(options)
        period = self._odr_sums(domain + self._odr_period_domain(options), 'account_id')
        initial = {}
        for initial_domain in self._odr_initial_domains(options, domain):
            self._odr_add(initial, self._odr_sums(initial_domain, 'account_id'))
        undistributed_domain = self._odr_undistributed_domain(options, domain)
        undistributed = self._odr_sums(undistributed_domain, 'company_id') if undistributed_domain else {}
        figures = {account_id: (initial.get(account_id, EMPTY), period.get(account_id, EMPTY))
                   for account_id in set(period) | set(initial)}
        return figures, sum(v['balance'] for v in undistributed.values())

    @api.model
    def _odr_shown(self, values, options, suffixes):
        """Whether an account passes the Accounts option in one of the periods."""
        currency = self._om_currency()
        for suffix in suffixes:
            if options['display_account'] == 'all':
                return True
            if options['display_account'] == 'not_zero':
                if not currency.is_zero(values['end_balance' + suffix]):
                    return True
            elif any(not currency.is_zero(values[key + suffix]) for key in AMOUNTS):
                return True
        return False

    @api.model
    def _odr_tree(self, options):
        periods = self._odr_period_options(options)
        suffixes = ['_%s' % index if index else '' for index in range(len(periods))]
        figures = [report._odr_period_figures(period) for report, period in self._odr_periods(options)]
        analytic = [report._odr_period_analytic(period) for report, period in self._odr_periods(options)]
        analytic_keys = [key for key, _label, _domain in self._odr_analytic_columns(options)]

        Account = self.env['account.account'].with_context(active_test=False)
        account_ids = set()
        for by_account, _undistributed in figures:
            account_ids |= set(by_account)
        for by_column in analytic:
            for by_account in by_column.values():
                account_ids |= set(by_account)
        if options['display_account'] == 'all':
            account_domain = [('company_ids', 'parent_of', self.env.companies.ids)]
            if options['account_ids']:
                account_domain.append(('id', 'in', options['account_ids']))
            if options['account_tag_ids']:
                account_domain.append(('tag_ids', 'in', options['account_tag_ids']))
            account_ids |= set(Account.search(account_domain).ids)
        accounts = Account.browse(account_ids).sorted(self._odr_account_sort)

        leaves = []
        for account in accounts:
            values = {}
            for suffix, (by_account, _undistributed), by_column in zip(suffixes, figures, analytic):
                values.update(self._odr_values(*by_account.get(account.id, (EMPTY, EMPTY)), suffix=suffix))
                for key in analytic_keys:
                    values['an_%s%s' % (key, suffix)] = by_column[key].get(account.id, 0.0)
            if self._odr_shown(values, options, suffixes):
                leaves.append((account, values))

        sum_keys = [key + suffix for suffix in suffixes for key in AMOUNTS]
        sum_keys += ['an_%s%s' % (key, suffix) for suffix in suffixes for key in analytic_keys]
        tree = self._odr_group_accounts(
            leaves, options, lambda account, values, parent_id, level:
            self._odr_account_node(account, values, options, parent_id, level), sum_keys)

        currency = self._om_currency()
        if any(not currency.is_zero(undistributed) for _figures, undistributed in figures):
            values = {}
            for suffix, (_by_account, undistributed) in zip(suffixes, figures):
                values.update(self._odr_values({**EMPTY, 'balance': undistributed}, EMPTY, suffix=suffix))
            name = self.env._("Undistributed Profits/Losses")
            tree.append(self._odr_node('undistributed', name, self._om_line(
                'undistributed', name, values, kind='leaf',
                help=self.env._("The income and expense of the previous fiscal years."))))
            leaves.append((False, values))
        if not leaves:
            return [], False
        # the split columns of the total are the totals of the split columns, not a split of the total
        return tree, {key: sum(values.get(key, 0.0) for _account, values in leaves) for key in sum_keys}

    @api.model
    def _odr_account_node(self, account, values, options, parent_id=False, level=0):
        line_id = '%s|account-%s' % (parent_id, account.id) if parent_id else 'account-%s' % account.id
        name = self._odr_account_name(account)
        general_ledger = self._om_link('om.dynamic.report.general.ledger', self.env._("Open General Ledger"), {
            'account_ids': [account.id], 'journal_ids': options['journal_ids'],
            'target_move': options['target_move'], 'analytic_account_ids': options.get('analytic_account_ids', []),
        }, icon='menu_book')
        line = self._om_line(line_id, name, values, parent_id=parent_id, level=level, kind='leaf',
                             drill=True, drill_label=self.env._("Journal items of the period"),
                             links=[general_ledger])
        return self._odr_node(line_id, name, line)

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        """The journal items of one figure: of the initial balance, of the period, of the ending
        balance (both), or the analytic lines of an analytic column, for the period of the column."""
        account_id = self._odr_line_id_part(line_id, 'account')
        if not account_id:
            return False
        account = self.env['account.account'].browse(account_id)
        key, period = self._odr_cell_scope(options, column_key)
        label = self._om_period_label(period)
        if key.startswith('an_'):
            return self._odr_analytic_cell_action(options, key, account, self._odr_period_domain(period),
                                                  '%s - %s' % (account.display_name, label))
        domain = self._odr_domain(period)
        movements = [domain + self._odr_period_domain(period)]
        initial = self._odr_initial_domains(period, domain)
        if key.startswith('init_'):
            parts, label = initial, self.env._("Initial balance")
        elif key.startswith('end_'):
            parts, label = initial + movements, self.env._("Ending balance")
        else:
            parts = movements
        if not parts:
            return False
        scope = Domain.OR(parts) & Domain('account_id', '=', account_id)
        return self._odr_journal_items_action(list(scope), '%s - %s' % (account.display_name, label))

    @api.model
    def _om_line_action(self, options, line_id):
        account_id = self._odr_line_id_part(line_id, 'account')
        if not account_id:
            return False
        account = self.env['account.account'].browse(account_id)
        domain = self._odr_domain(options) + self._odr_period_domain(options) + [('account_id', '=', account_id)]
        return self._odr_journal_items_action(domain, account.display_name)
