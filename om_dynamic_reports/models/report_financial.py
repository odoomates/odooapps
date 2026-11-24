from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

EMPTY = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}


class OmDynamicReportFinancial(models.AbstractModel):
    """A financial statement drawn from a tree of account.financial.report
    sections (Accounting Financial Reports): the sections in their order, each
    unfolding into its sub-sections and accounts, with the sign of the section,
    debit and credit on demand, and the earlier periods side by side.

    A section's amount is, by its type: the sum of its accounts ('accounts'),
    of the accounts of its account types ('account_type'), the amount of
    another section ('account_report'), or the sum of its children ('sum') --
    the same computation as the PDF report.

    A statement sets the root section in _odr_root_report.
    """
    _name = 'om.dynamic.report.financial'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Financial Statement'

    _report_section = 'statements'
    _report_compare = True
    # the root section's amount closes the report (Net Profit), or not (a balance sheet adds up to zero)
    _odr_root_total = True
    _odr_horizontal = True

    @api.model
    def _odr_root_report(self):
        return self.env['account.financial.report']

    @api.model
    def _odr_closes(self, root):
        """Whether the amount of the root section closes the report as its last line."""
        return self._odr_root_total

    @api.model
    def _om_name_label(self, options):
        return ''

    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids', 'analytic_account_ids', 'aml_filter_ids') + self._odr_analytic_column_filters()

    @api.model
    def _om_toggles(self):
        return [
            {'key': 'debit_credit', 'label': self.env._("Show debit and credit"), 'default': False,
             'help': self.env._("The debit and credit of the period next to the balance.")},
            {'key': 'hide_zero', 'label': self.env._("Hide accounts at zero"), 'default': True},
        ]

    @api.model
    def _om_choices(self):
        return [self._odr_target_move_choice(), *self._odr_horizontal_choice()]

    @api.model
    def _om_get_columns(self, options):
        columns = []
        if options['debit_credit']:
            columns += [
                {'key': 'debit', 'label': self.env._("Debit"), 'type': 'monetary', 'drill': True},
                {'key': 'credit', 'label': self.env._("Credit"), 'type': 'monetary', 'drill': True},
            ]
        periods = self._om_compare_periods(options)
        split = self._odr_split_columns(options)
        if split:
            # per period, a column per value of the horizontal group or per analytic account or plan,
            # then the total of the period
            for index, period in enumerate([options] + periods):
                suffix = '_%s' % index if index else ''
                group = self._om_period_label(period)
                for key, label in split:
                    columns.append({'key': key + suffix, 'label': label, 'type': 'monetary',
                                    'group': group, 'drill': True})
                columns.append({'key': 'balance' + suffix, 'label': self.env._("Total"), 'type': 'monetary',
                                'group': group, 'optional': False, 'drill': True,
                                'help': self._odr_split_total_help(options)})
            return columns
        columns.append({'key': 'balance', 'type': 'monetary', 'optional': False, 'drill': True,
                        'label': self._om_period_label(options) if periods else self.env._("Balance")})
        for index, period in enumerate(periods, start=1):
            columns.append({'key': 'balance_%s' % index, 'label': period['label'], 'type': 'monetary',
                            'optional': False, 'drill': True})
        if len(periods) == 1:
            columns.append({'key': 'variation', 'label': self.env._("Variation %"), 'type': 'percent',
                            'help': self.env._("Change from the compared period to this one.")})
        return columns

    # ------------------------------------------------------------------
    # Amounts
    # ------------------------------------------------------------------

    @api.model
    def _odr_account_sums(self, options, extra=()):
        """{account id: {'debit', 'credit', 'balance'}} of the period of ``options``: the flows of a
        period at the average rates of their months; the balances at a date at its rate, but for the
        income and expense in them, at the rates they were earned at (IAS 21). With ``extra``
        fields, by (account id, their values)."""
        domain = self._odr_domain(options) + self._odr_period_domain(options)
        groupbys = ['account_id', *extra]
        if self._report_date_mode != 'as_of':
            sums = self._odr_grouped_sums(domain, groupbys, flow=True)
        else:
            sums = self._odr_grouped_sums(domain, groupbys)
            if self._odr_converts():
                Account = self.env['account.account'].with_context(active_test=False)
                earned = [account.id for account in Account.browse({key[0] for key in sums})
                          if account.internal_group in ('income', 'expense')]
                if earned:
                    sums.update(self._odr_grouped_sums(domain + [('account_id', 'in', earned)], groupbys, flow=True))
        return sums if extra else {key[0]: values for key, values in sums.items()}

    @api.model
    def _odr_horizontal_scope(self, options):
        # the values of the columns are those of the accounts of the statement only
        domain = super()._odr_horizontal_scope(options)
        sections = self._odr_root_report()._get_children_by_order()
        account_ids = sections.filtered(lambda s: s.type == 'accounts').account_ids.ids
        types = sections.filtered(lambda s: s.type == 'account_type').account_type_ids.mapped('type')
        return domain + ['|', ('account_id', 'in', account_ids), ('account_id.account_type', 'in', types)]

    @api.model
    def _odr_rates_label(self, options):
        return self.env._(
            "%(currency)s: balances at the rates of %(date)s, income, expenses and cash flows at the average "
            "rates of their months", currency=self._om_currency().name,
            date=self._om_format_date(self.env.context.get('odr_rate_date') or options.get('date_to')))

    @api.model
    def _odr_translation_anchor(self, root):
        """The section the currency translation adjustment goes in: the one holding the profit
        (loss) to report, the equity."""
        for section in root._get_children_by_order():
            if section.type == 'account_report' and section.parent_id:
                return section.parent_id
        return root

    @api.model
    def _odr_section_accounts(self, section, account_sums):
        """The ids of the accounts making the amount of a section of type accounts or account_type."""
        if section.type == 'accounts':
            return set(section.account_ids.ids)
        if section.type == 'account_type':
            types = set(section.account_type_ids.mapped('type'))
            Account = self.env['account.account'].with_context(active_test=False)
            return {account.id for account in Account.browse(list(account_sums)) if account.account_type in types}
        return set()

    @api.model
    def _odr_section_amounts(self, sections, account_sums):
        """{section id: {'debit', 'credit', 'balance', 'accounts': {account id: sums}}}, unsigned."""
        result = {}

        def compute(section):
            if section.id in result:
                return result[section.id]
            # a placeholder first: the constraints of the model forbid cycles, this guards the data anyway
            result[section.id] = {**EMPTY, 'accounts': {}}
            amounts = {**EMPTY, 'accounts': {}}
            if section.type in ('accounts', 'account_type'):
                for account_id in self._odr_section_accounts(section, account_sums):
                    sums = account_sums.get(account_id, EMPTY)
                    amounts['accounts'][account_id] = sums
                    for key in EMPTY:
                        amounts[key] += sums[key]
            elif section.type == 'account_report' and section.account_report_id:
                source = compute(section.account_report_id)
                for key in EMPTY:
                    amounts[key] = source[key]
            elif section.type == 'sum':
                for child in section.children_ids:
                    child_amounts = compute(child)
                    for key in EMPTY:
                        amounts[key] += child_amounts[key]
            result[section.id] = amounts
            return amounts

        for section in sections:
            compute(section)
        return result

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    @api.model
    def _odr_extra_columns(self, options, index, period, account_sums):
        """{column key: {account id: {'debit', 'credit', 'balance'}}} of columns of a period other modules add,
        e.g. the budget, summed per section like the balance.

        :param index: the rank of the period, 0 for the period of the report
        :param account_sums: the sums of the period per account
        """
        return {}

    @api.model
    def _odr_values(self, amounts_by_period, sign, options, account_id=False):
        """The columns of a section (or of one of its accounts) over the periods; each period gives
        {'total': amounts, 'columns': {split column key: amounts}}."""
        values = {}
        for index, period in enumerate(amounts_by_period):
            suffix = '_%s' % index if index else ''
            amounts = period['total']
            sums = amounts['accounts'].get(account_id, EMPTY) if account_id else amounts
            values['balance' + suffix] = sums['balance'] * sign or 0.0
            if index == 0:
                values['debit'] = sums['debit']
                values['credit'] = sums['credit']
            for key, column_amounts in period['columns'].items():
                column_sums = column_amounts['accounts'].get(account_id, EMPTY) if account_id else column_amounts
                values[key + suffix] = column_sums['balance'] * sign or 0.0
        if len(amounts_by_period) == 2:
            current, previous = values['balance'], values['balance_1']
            values['variation'] = (current - previous) / abs(previous) * 100 if previous else False
        return values

    @api.model
    def _odr_is_zero(self, values):
        currency = self._om_currency()
        return all(currency.is_zero(value) for key, value in values.items()
                   if key != 'variation' and isinstance(value, float))

    @api.model
    def _odr_tree(self, options):
        root = self._odr_root_report()
        if not root:
            return [], False
        sections = root._get_children_by_order()
        analytic = self._odr_analytic_columns(options)
        horizontal = self._odr_horizontal_names(options) if self._odr_horizontal_group(options) else []
        period_amounts = []
        translations = []
        flow = self._report_date_mode != 'as_of'
        for index, (report, period) in enumerate(self._odr_periods(options)):
            account_sums = report._odr_account_sums(period)
            if horizontal:
                split = report._odr_horizontal_split(options, report._odr_account_sums(period, horizontal))
            else:
                split = {'an_%s' % key: report._odr_analytic_sums(period, domain, self._odr_period_domain(period),
                                                                   flow=flow) for key, _label, domain in analytic}
            split.update(report._odr_extra_columns(options, index, period, account_sums))
            period_amounts.append({
                'total': self._odr_section_amounts(sections, account_sums),
                'columns': {key: self._odr_section_amounts(sections, sums) for key, sums in split.items()},
            })
            # converted at different rates, the balances no longer add up to zero: what is left is the
            # currency translation adjustment, in the equity
            translations.append(-sum(sums['balance'] for sums in account_sums.values())
                                if not flow and self._odr_converts() else 0.0)
        anchor = self._odr_translation_anchor(root)
        currency = self._om_currency()
        with_translation = any(not currency.is_zero(amount) for amount in translations)
        if with_translation:
            chain = anchor
            while chain:
                for amounts, translation in zip(period_amounts, translations):
                    if chain.id in amounts['total']:
                        amounts['total'][chain.id]['balance'] += translation
                chain = chain.parent_id

        def amounts_of(section):
            return [{'total': amounts['total'][section.id],
                     'columns': {key: column[section.id] for key, column in amounts['columns'].items()}}
                    for amounts in period_amounts]

        def build(section, parent_id, level):
            node_id = '%s|section-%s' % (parent_id, section.id) if parent_id else 'section-%s' % section.id
            sign = float(section.sign)
            children = []
            for child in section.children_ids.sorted(lambda s: (s.sequence, s.id)):
                children.append(build(child, node_id, level + 1))
            if section.display_detail != 'no_detail' and section.type in ('accounts', 'account_type'):
                account_ids = set()
                for amounts in amounts_of(section):
                    account_ids |= set(amounts['total']['accounts'])
                    for column in amounts['columns'].values():
                        account_ids |= set(column['accounts'])
                accounts = self.env['account.account'].with_context(active_test=False).browse(account_ids)
                for account in accounts.sorted(self._odr_account_sort):
                    values = self._odr_values(amounts_of(section), sign, options, account.id)
                    if options['hide_zero'] and self._odr_is_zero(values):
                        continue
                    children.append(self._odr_account_node(account, values, node_id, level + 1, options))
            if with_translation and section == anchor:
                translation_id = '%s|translation' % node_id
                name = self.env._("Currency translation adjustment")
                values = self._odr_values([{'total': {**EMPTY, 'balance': translation, 'accounts': {}}, 'columns': {}}
                                           for translation in translations], sign, options)
                children.append(self._odr_node(translation_id, name, self._om_line(
                    translation_id, name, values, parent_id=node_id, level=level + 1, kind='leaf',
                    help=self.env._("The difference of the balances at the closing rate and of the result at "
                                    "the rates it was earned at."))))
            values = self._odr_values(amounts_of(section), sign, options)
            line = self._om_line(node_id, section.name, values, parent_id=parent_id, level=level,
                                 kind='group', has_children=bool(children),
                                 count=len(children), unfolded=True)
            return self._odr_node(node_id, section.name, line, children)

        tree = [build(section, False, 0) for section in root.children_ids.sorted(lambda s: (s.sequence, s.id))]
        total = False
        if self._odr_closes(root):
            total = self._odr_values(amounts_of(root), float(root.sign), options)
        return tree, total

    @api.model
    def _odr_account_node(self, account, values, parent_id, level, options):
        line_id = '%s|account-%s' % (parent_id, account.id)
        name = self._odr_account_name(account)
        link_options = {'account_ids': [account.id], 'journal_ids': options['journal_ids'],
                        'target_move': options['target_move']}
        if self._report_date_mode == 'as_of':
            # the ledger of the year up to the date
            link_options.update(date_preset='custom', date_to=options['date_to'],
                                date_from=str(self._odr_fiscal_year_start(options['date_to'])))
        general_ledger = self._om_link('om.dynamic.report.general.ledger', self.env._("Open General Ledger"),
                                       link_options, icon='menu_book')
        line = self._om_line(line_id, name, values, parent_id=parent_id, level=level, kind='leaf', drill=True,
                             drill_label=self.env._("Journal items"), links=[general_ledger])
        return self._odr_node(line_id, name, line)

    @api.model
    def _om_total(self, data, options):
        if not data.get('total'):
            return False
        root = self._odr_root_report()
        return self._om_line('total', self._odr_total_label(root), data['total'], kind='total')

    @api.model
    def _odr_total_label(self, root):
        return root.name

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        account_id = self._odr_line_id_part(line_id, 'account')
        if not account_id:
            return False
        account = self.env['account.account'].browse(account_id)
        key, period = self._odr_cell_scope(options, column_key)
        name = '%s - %s' % (account.display_name, self._om_period_label(period))
        if key.startswith('an_'):
            return self._odr_analytic_cell_action(options, key, account, self._odr_period_domain(period), name)
        domain = self._odr_domain(period) + self._odr_period_domain(period) + [('account_id', '=', account_id)]
        if key.startswith('hg_'):
            column_domain = self._odr_horizontal_cell_domain(options, key)
            if column_domain is False:
                return False
            domain += column_domain
        return self._odr_journal_items_action(domain, name)

    @api.model
    def _om_line_action(self, options, line_id):
        account_id = self._odr_line_id_part(line_id, 'account')
        if not account_id:
            return False
        account = self.env['account.account'].browse(account_id)
        domain = self._odr_domain(options) + self._odr_period_domain(options) + [('account_id', '=', account_id)]
        return self._odr_journal_items_action(domain, account.display_name)


class OmDynamicReportBalanceSheet(models.AbstractModel):
    """Balance Sheet at a date: the whole history up to it, the result of the
    years included in the profit (loss) to report, as in the PDF report."""
    _name = 'om.dynamic.report.balance.sheet'
    _inherit = 'om.dynamic.report.financial'
    _description = 'Dynamic Balance Sheet'

    _report_name = 'Balance Sheet'
    _report_description = _lt("Assets, liabilities and equity at a date.")
    _report_sequence = 1
    _report_icon = 'account_balance'
    _report_date_mode = 'as_of'
    _report_default_preset = 'today'
    _odr_root_total = False

    @api.model
    def _om_report_title(self):
        return self.env._("Balance Sheet")

    @api.model
    def _odr_root_report(self):
        return self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0',
                            raise_if_not_found=False) or self.env['account.financial.report']

    @api.model
    def _om_compare_choices(self):
        return [
            {'key': 'previous_year', 'label': self.env._("Same date last year")},
            {'key': 'previous_period', 'label': self.env._("Previous month end")},
        ]


class OmDynamicReportProfitLoss(models.AbstractModel):
    """Profit and Loss over a period, closed by the net profit."""
    _name = 'om.dynamic.report.profit.loss'
    _inherit = 'om.dynamic.report.financial'
    _description = 'Dynamic Profit and Loss'

    _report_name = 'Profit and Loss'
    _report_description = _lt("Income and expense of a period, and the net profit.")
    _report_sequence = 2
    _report_icon = 'monitoring'

    @api.model
    def _om_report_title(self):
        return self.env._("Profit and Loss")

    @api.model
    def _odr_root_report(self):
        return self.env.ref('accounting_pdf_reports.account_financial_report_profitandloss0',
                            raise_if_not_found=False) or self.env['account.financial.report']

    @api.model
    def _odr_total_label(self, root):
        return self.env._("Net Profit")
