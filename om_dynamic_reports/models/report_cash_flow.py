from odoo import api, models, _, _lt

# the lines of the indirect method, by section, in order
INDIRECT_LINES = {
    'operating': ('net_profit', 'depreciation', 'receivable', 'payable', 'current_asset', 'current_liability',
                  'credit_card', 'other'),
    'investing': ('fixed_asset', 'other'),
    'financing': ('borrowing', 'equity', 'other'),
}


class OmDynamicReportCashFlow(models.AbstractModel):
    """Cash Flow Statement, direct method: the cash received and paid in the
    period, by what it was received or paid for, in the operating, investing
    and financing sections, between the cash at the start and at the end.

    The cash is followed through the transit accounts (outstanding receipts and
    payments, suspense, internal transfers) to what it settled; this is the
    computation of the PDF Cash Flow Statement, called for each period shown.
    """
    _name = 'om.dynamic.report.cash.flow'
    _inherit = 'om.dynamic.report.financial'
    _description = 'Dynamic Cash Flow Statement'

    _report_name = 'Cash Flow Statement'
    _report_description = _lt("Cash received and paid, by operating, investing and financing activities.")
    _report_sequence = 3
    _report_icon = 'payments'
    _odr_root_total = False
    _odr_horizontal = False

    @api.model
    def _om_report_title(self):
        return _("Cash Flow Statement")

    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids')

    @api.model
    def _om_choices(self):
        return [
            {'key': 'method', 'label': _("Method"), 'icon': 'account_tree', 'menu': 'bar',
             'default': 'direct', 'choices': [['direct', _("Direct method")],
                                              ['indirect', _("Indirect method")]]},
            *super()._om_choices(),
        ]

    @api.model
    def _om_toggles(self):
        return [{'key': 'hide_zero', 'label': _("Hide accounts at zero"), 'default': True}]

    @api.model
    def _om_get_columns(self, options):
        return super()._om_get_columns({**options, 'debit_credit': False})

    @api.model
    def _om_clean_options(self, options):
        options['debit_credit'] = False
        return options

    @api.model
    def _om_default_options(self):
        return {**super()._om_default_options(), 'debit_credit': False}

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_cash_flow(self, options):
        if options.get('method') == 'indirect':
            return self._odr_indirect_cash_flow(options)
        return self._odr_direct_cash_flow(options)

    @api.model
    def _odr_direct_cash_flow(self, options):
        """The statement of one period, as the PDF report computes it: for each company selected
        (with its branches), its amounts converted to the currency of the report, then added up."""
        self.env.flush_all()
        companies = self.env.companies
        roots = companies.filtered(lambda c: not (c.parent_ids - c) & companies)
        merged = None
        for company in roots:
            company = company.with_context(odr_period=(options['date_from'], options['date_to']))
            cash_flow = self.env['report.accounting_pdf_reports.report_cash_flow']._get_cash_flow({
                'company_id': company.id,
                'date_from': options['date_from'],
                'date_to': options['date_to'],
                'target_move': options['target_move'],
                'journal_ids': options['journal_ids'],
            })
            merged = self._odr_merge_cash_flow(merged, cash_flow, company)
        return merged

    @api.model
    def _odr_indirect_labels(self):
        return {
            'net_profit': _("Net profit"),
            'depreciation': _("Depreciation and amortisation (non-cash)"),
            'receivable': _("Decrease (increase) in receivables"),
            'payable': _("Increase (decrease) in payables"),
            'current_asset': _("Decrease (increase) in other current assets"),
            'current_liability': _("Increase (decrease) in taxes, salaries and other current liabilities"),
            'credit_card': _("Increase (decrease) in credit cards"),
            'fixed_asset': _("Fixed and non-current assets"),
            'borrowing': _("Borrowings"),
            'equity': _("Equity"),
            'other': _("Other"),
        }

    @api.model
    def _odr_indirect_cash_flow(self, options):
        """The statement of one period by the indirect method: the net profit, then the change of
        every account that is neither cash nor income and expense. A journal item moves cash
        when, and only when, its entry changes the other accounts the other way: the statement adds
        up to the change of the cash. Depreciation is added back in the operating activities and
        taken out of the fixed assets, where its accumulated depreciation is."""
        # the change of the cash comes from every entry, whichever journal it is in
        all_journals = {**options, 'journal_ids': []}
        domain = self._odr_domain(all_journals)
        movements = self._odr_sums(domain + self._odr_period_domain(options), 'account_id', flow=True)
        cash_domain = domain + [('account_id.account_type', '=', 'asset_cash')]
        # the cash at the start at the rate of that day, at the end at the closing rate
        opening = sum(v['balance'] for v in self.with_context(
            odr_rate_date=self._odr_day_before(options['date_from']))._odr_sums(
            cash_domain + [('date', '<', options['date_from'])], 'company_id').values())
        closing = sum(v['balance'] for v in self._odr_sums(
            cash_domain + [('date', '<=', options['date_to'])], 'company_id').values())
        classify = self.env['report.accounting_pdf_reports.report_cash_flow']._classify
        Account = self.env['account.account'].with_context(active_test=False)
        flows = {}

        def add(activity, line, account, amount):
            entry = flows.setdefault(activity, {}).setdefault(line, {'amount': 0.0, 'accounts': {}})
            entry['amount'] += amount
            key = account.id if account else 'depreciation'
            item = entry['accounts'].setdefault(key, {
                'code': self._odr_account_code(account) if account else '',
                'name': account.name if account else _("Less depreciation (non-cash)"),
                'amount': 0.0})
            item['amount'] += amount

        depreciation = 0.0
        net_change = 0.0
        for account in Account.browse(list(movements)):
            balance = movements[account.id]['balance']
            if account.account_type == 'asset_cash':
                net_change += balance
            elif account.internal_group in ('income', 'expense'):
                # what the period earned: the net profit, its accounts underneath
                add('operating', 'net_profit', account, -balance)
                if account.account_type == 'expense_depreciation':
                    depreciation += balance
                    add('operating', 'depreciation', account, balance)
            else:
                activity, line = classify(account)
                if line not in INDIRECT_LINES.get(activity, ()):
                    line = 'other'
                add(activity, line, account, -balance)
        if depreciation and 'fixed_asset' in flows.get('investing', {}):
            add('investing', 'fixed_asset', False, -depreciation)
        elif depreciation:
            # no fixed asset moved: the accumulated depreciation is elsewhere, the add-back is undone there
            add('operating', 'depreciation', False, -depreciation)

        currency = self._om_currency()
        labels = self._odr_indirect_labels()
        sections = []
        for activity, activity_name in self.env['account.account']._fields[
                'cash_flow_activity']._description_selection(self.env):
            lines = []
            for key in INDIRECT_LINES[activity]:
                entry = flows.get(activity, {}).get(key)
                if not entry:
                    continue
                accounts = sorted(({'code': item['code'], 'name': item['name'],
                                    'amount': currency.round(item['amount'])}
                                   for item in entry['accounts'].values()), key=lambda item: (not item['code'],
                                                                                              item['code']))
                lines.append({'key': key, 'name': labels[key], 'amount': currency.round(entry['amount']),
                              'accounts': accounts})
            sections.append({'activity': activity, 'name': activity_name, 'lines': lines,
                             'total': currency.round(sum(line['amount'] for line in lines))})
        return {
            'sections': sections,
            'opening': currency.round(opening),
            'net_change': currency.round(net_change),
            'fx_effect': currency.round(closing - opening - net_change),
            'closing': currency.round(closing),
        }

    @api.model
    def _odr_merge_cash_flow(self, merged, cash_flow, company):
        """Add a company's statement, converted, to the statement of the companies before it: the
        flows at the average rate of the period, the cash at the start at its rate, the cash at the
        end at the closing rate; what the rates did to the cash is a line of its own."""
        date_from, date_to = company.env.context['odr_period']
        factor = self._odr_average_factor(company.currency_id, date_from, date_to)
        convert = lambda amount: amount * factor  # noqa: E731
        if merged is None:
            merged = {'opening': 0.0, 'net_change': 0.0, 'closing': 0.0, 'fx_effect': 0.0, 'sections': []}
        opening = self._odr_convert(cash_flow['opening'], company, self._odr_day_before(date_from))
        closing = self._odr_convert(cash_flow['closing'], company)
        net_change = convert(cash_flow['net_change'])
        merged['opening'] += opening
        merged['closing'] += closing
        merged['net_change'] += net_change
        merged['fx_effect'] += closing - opening - net_change
        for section in cash_flow['sections']:
            target = next((s for s in merged['sections'] if s['activity'] == section['activity']), None)
            if not target:
                target = {'activity': section['activity'], 'name': section['name'], 'total': 0.0, 'lines': []}
                merged['sections'].append(target)
            target['total'] += convert(section['total'])
            for line in section['lines']:
                target_line = next((l for l in target['lines'] if l['key'] == line['key']), None)
                if not target_line:
                    target_line = {'key': line['key'], 'name': line['name'], 'amount': 0.0, 'accounts': []}
                    target['lines'].append(target_line)
                target_line['amount'] += convert(line['amount'])
                for account in line['accounts']:
                    target_account = next((a for a in target_line['accounts'] if a['code'] == account['code']), None)
                    if not target_account:
                        target_account = {'code': account['code'], 'name': account['name'], 'amount': 0.0}
                        target_line['accounts'].append(target_account)
                    target_account['amount'] += convert(account['amount'])
        return merged

    @api.model
    def _odr_columns_of(self, amounts):
        """{'balance': ..., 'balance_1': ..., 'variation': ...} from the amounts of the periods, in order."""
        values = {}
        for index, amount in enumerate(amounts):
            values['balance' if index == 0 else 'balance_%s' % index] = amount or 0.0
        if len(amounts) == 2:
            current, previous = amounts
            values['variation'] = (current - previous) / abs(previous) * 100 if previous else False
        return values

    @api.model
    def _odr_tree(self, options):
        periods = [report._odr_cash_flow(period) for report, period in self._odr_periods(options)]
        count = len(periods)
        Account = self.env['account.account'].with_context(active_test=False)
        accounts_by_code = {}

        def account_of(code):
            if not code:
                return Account
            if code not in accounts_by_code:
                accounts_by_code[code] = Account.search(
                    [('code', '=', code), ('company_id', 'parent_of', self.env.companies.ids)], limit=1)
            return accounts_by_code[code]

        # the sections, lines and accounts of every period, in the order of the statement
        structure = {}
        for index, cash_flow in enumerate(periods):
            for section in cash_flow['sections']:
                entry = structure.setdefault(section['activity'], {
                    'name': section['name'], 'totals': [0.0] * count, 'lines': {}})
                entry['totals'][index] = section['total']
                for line in section['lines']:
                    line_entry = entry['lines'].setdefault(line['key'], {
                        'name': line['name'], 'amounts': [0.0] * count, 'accounts': {}})
                    line_entry['amounts'][index] = line['amount']
                    for account in line['accounts']:
                        account_entry = line_entry['accounts'].setdefault(account['code'], {
                            'name': ' '.join(part for part in (account['code'], account['name']) if part),
                            'amounts': [0.0] * count})
                        account_entry['amounts'][index] = account['amount']

        nodes = [self._odr_cash_node('opening', _("Cash at the beginning of the period"),
                                     [p['opening'] for p in periods], kind='opening', drill=True)]
        for activity, section in structure.items():
            section_id = 'activity-%s' % activity
            line_nodes = []
            for line_key, line in section['lines'].items():
                line_id = '%s|line-%s' % (section_id, line_key)
                account_nodes = []
                for code, account in sorted(line['accounts'].items()):
                    values = self._odr_columns_of(account['amounts'])
                    if options['hide_zero'] and self._odr_is_zero(values):
                        continue
                    record = account_of(code)
                    account_id = '%s|account-%s' % (line_id, record.id or 0)
                    account_nodes.append(self._odr_node(account_id, account['name'], self._om_line(
                        account_id, account['name'], values, parent_id=line_id, level=2, kind='leaf',
                        drill=bool(record), drill_label=_("Journal items of the account"))))
                line_nodes.append(self._odr_node(line_id, line['name'], self._om_line(
                    line_id, line['name'], self._odr_columns_of(line['amounts']), parent_id=section_id, level=1,
                    kind='group' if account_nodes else 'leaf', has_children=bool(account_nodes),
                    count=len(account_nodes)), account_nodes))
            nodes.append(self._odr_node(section_id, section['name'], self._om_line(
                section_id, section['name'], self._odr_columns_of(section['totals']), kind='group',
                has_children=bool(line_nodes), count=len(line_nodes), unfolded=True), line_nodes))
        nodes.append(self._odr_cash_node('net_change', _("Net change in cash"),
                                         [p['net_change'] for p in periods], kind='group', drill=True))
        currency = self._om_currency()
        if any(not currency.is_zero(p.get('fx_effect') or 0.0) for p in periods):
            nodes.append(self._odr_cash_node('fx_effect', _("Effect of exchange rate changes on cash"),
                                             [p.get('fx_effect') or 0.0 for p in periods], kind='leaf'))
        return nodes, self._odr_columns_of([p['closing'] for p in periods])

    @api.model
    def _odr_cash_node(self, key, name, amounts, kind, drill=False):
        line = self._om_line(key, name, self._odr_columns_of(amounts), kind=kind, drill=drill,
                             drill_label=_("Cash entries"))
        return self._odr_node(key, name, line)

    @api.model
    def _om_total(self, data, options):
        if not data.get('total'):
            return False
        return self._om_line('total', _("Cash at the end of the period"), data['total'], kind='total')

    @api.model
    def _odr_cash_domain(self, options):
        domain = [('company_id', 'in', self._odr_company_ids()), ('account_id.account_type', '=', 'asset_cash'),
                  ('parent_state', '=', 'posted') if options['target_move'] == 'posted'
                  else ('parent_state', 'in', ('draft', 'posted'))]
        if options['journal_ids']:
            domain.append(('journal_id', 'in', options['journal_ids']))
        return domain

    @api.model
    def _om_line_action(self, options, line_id):
        if line_id == 'opening':
            return self._odr_journal_items_action(
                self._odr_cash_domain(options) + [('date', '<', options['date_from'])],
                _("Cash at the beginning of the period"))
        if line_id == 'net_change':
            return self._odr_journal_items_action(
                self._odr_cash_domain(options) + self._odr_period_domain(options), _("Cash entries"))
        account_id = self._odr_line_id_part(line_id, 'account')
        if not account_id:
            return False
        account = self.env['account.account'].browse(account_id)
        domain = self._odr_domain(options) + self._odr_period_domain(options) + [('account_id', '=', account_id)]
        return self._odr_journal_items_action(domain, account.display_name)
