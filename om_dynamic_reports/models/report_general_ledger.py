from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

ORDERS = {
    'date': 'date, move_name, id',
    'journal_partner': 'journal_id, partner_id, date, move_name, id',
}


class OmDynamicReportGeneralLedger(models.AbstractModel):
    """General Ledger: every account with its debit, credit and balance; an
    account unfolds into its initial balance and its journal items, with the
    running balance, page by page."""
    _name = 'om.dynamic.report.general.ledger'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic General Ledger'

    _report_name = 'General Ledger'
    _report_description = _lt("Every account with its journal items and running balance.")
    _report_section = 'ledgers'
    _report_sequence = 20
    _report_icon = 'menu_book'

    @api.model
    def _om_report_title(self):
        return self.env._("General Ledger")

    @api.model
    def _om_name_label(self, options):
        return self.env._("Account")

    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids', 'account_ids', 'account_tag_ids', 'partner_ids',
                                 'analytic_account_ids')

    @api.model
    def _om_toggles(self):
        return [{'key': 'initial_balance', 'label': self.env._("Initial balance"), 'default': True,
                 'help': self.env._("Start each account with its balance before the period.")}]

    @api.model
    def _om_choices(self):
        return [
            self._odr_target_move_choice(),
            {'key': 'display_account', 'label': self.env._("Accounts"), 'default': 'movement', 'choices': [
                ('movement', self.env._("With movements")),
                ('not_zero', self.env._("With balance not zero")),
                ('all', self.env._("All accounts")),
            ]},
            {'key': 'sortby', 'label': self.env._("Sort journal items by"), 'default': 'date', 'choices': [
                ('date', self.env._("Date")),
                ('journal_partner', self.env._("Journal and partner")),
            ]},
            self._odr_hierarchy_choice(with_type=False),
        ]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': self.env._("Date"), 'type': 'date', 'detail_only': True},
            {'key': 'journal', 'label': self.env._("Journal"), 'type': 'char', 'detail_only': True},
            {'key': 'partner', 'label': self.env._("Partner"), 'type': 'char', 'detail_only': True},
            {'key': 'label', 'label': self.env._("Label"), 'type': 'char', 'detail_only': True},
            {'key': 'matching', 'label': self.env._("Matching"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'amount_currency', 'label': self.env._("Amount in Currency"), 'type': 'float',
             'detail_only': True, 'visible': False},
            {'key': 'currency', 'label': self.env._("Currency"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'debit', 'label': self.env._("Debit"), 'type': 'monetary', 'blank_zero': True},
            {'key': 'credit', 'label': self.env._("Credit"), 'type': 'monetary', 'blank_zero': True},
            {'key': 'balance', 'label': self.env._("Balance"), 'type': 'monetary'},
        ]

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_initial(self, options, domain):
        initial = {}
        if options['initial_balance']:
            for initial_domain in self._odr_initial_domains(options, domain):
                self._odr_add(initial, self._odr_sums(initial_domain, 'account_id'))
        return initial

    @api.model
    def _odr_tree(self, options):
        empty = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
        domain = self._odr_domain(options)
        period = self._odr_sums(domain + self._odr_period_domain(options), 'account_id')
        initial = self._odr_initial(options, domain)
        Account = self.env['account.account'].with_context(active_test=False)
        account_ids = set(period) | set(initial)
        if options['display_account'] == 'all':
            account_domain = [('company_ids', 'parent_of', self.env.companies.ids)]
            if options['account_ids']:
                account_domain.append(('id', 'in', options['account_ids']))
            account_ids |= set(Account.search(account_domain).ids)
        accounts = Account.browse(account_ids).sorted(self._odr_account_sort)
        currency = self._om_currency()
        entries = []
        total = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
        for account in accounts:
            opening = initial.get(account.id, empty)
            moves = period.get(account.id, empty)
            values = {key: opening[key] + moves[key] for key in ('debit', 'credit', 'balance')}
            if options['display_account'] == 'movement' and account.id not in period and \
                    currency.is_zero(opening['balance']):
                continue
            if options['display_account'] == 'not_zero' and currency.is_zero(values['balance']):
                continue
            values['_unfold'] = account.id in period or not currency.is_zero(opening['balance'])
            values['_opening'] = opening if account.id in initial else False
            entries.append((account, values))
            for key in total:
                total[key] += values[key]

        nodes = self._odr_group_accounts(entries, options, self._odr_account_leaf, ('debit', 'credit', 'balance'))
        undistributed_domain = self._odr_undistributed_domain(options, domain) if options['initial_balance'] else False
        if undistributed_domain:
            sums = self._odr_sums(undistributed_domain, 'company_id')
            values = {key: sum(v[key] for v in sums.values()) for key in ('debit', 'credit', 'balance')}
            if not currency.is_zero(values['debit']) or not currency.is_zero(values['credit']):
                name = self.env._("Undistributed Profits/Losses")
                nodes.append(self._odr_node('undistributed', name, self._om_line(
                    'undistributed', name, values, kind='leaf')))
                for key in total:
                    total[key] += values[key]
        return nodes, total if nodes else False

    @api.model
    def _odr_account_leaf(self, account, values, parent_id, level):
        values = dict(values)
        unfold, opening = values.pop('_unfold'), values.pop('_opening')
        line_id = '%s|account-%s' % (parent_id, account.id) if parent_id else 'account-%s' % account.id
        name = self._odr_account_name(account)
        line = self._om_line(line_id, name, values, parent_id=parent_id, level=level, kind='leaf',
                             has_children=unfold, drill=True,
                             drill_label=self.env._("Journal items of the period"), opening=opening)
        return self._odr_node(line_id, name, line)

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        account_id = self._odr_line_id_part(line['id'], 'account')
        if not account_id:
            return [], 0
        domain = self._odr_domain(options) + self._odr_period_domain(options) + [('account_id', '=', account_id)]
        opening = line.get('opening') if options['initial_balance'] else False
        return self._odr_item_lines(line, domain, opening, ORDERS[options['sortby']], offset, limit)

    @api.model
    def _om_line_action(self, options, line_id):
        account_id = self._odr_line_id_part(line_id, 'account')
        if not account_id:
            return False
        account = self.env['account.account'].browse(account_id)
        domain = self._odr_domain(options) + self._odr_period_domain(options) + [('account_id', '=', account_id)]
        return self._odr_journal_items_action(domain, account.display_name)
