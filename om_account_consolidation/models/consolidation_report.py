from collections import defaultdict

from odoo import api, models
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from odoo.addons.om_report_engine.models.report import PAGE_SIZE

_lt = LazyTranslate(__name__)

SIGNS = {'asset': 1, 'expense': 1, 'liability': -1, 'equity': -1, 'income': -1}


class OmConsolidationReport(models.AbstractModel):
    """What the consolidated reports share: the period they show, a column per company translated into
    the group currency, the eliminations, the adjustments and the group total, a period to compare with,
    and the journal items behind a figure of a company.

    A node is {'id', 'name', 'line', 'children'}; the ids of the children start with the id of their
    parent and a '|'."""
    _name = 'om.consolidation.report'
    _inherit = 'om.report'
    _description = 'Consolidated Report'

    _report_app = 'accounting'
    _report_section = 'consolidation'
    _report_group = 'account.group_account_readonly,account.group_account_manager'
    _report_date_mode = 'none'
    _report_rounding = True
    # the group accounts of the report, by type, and how the figures are signed
    _ocr_kinds = ('asset', 'liability', 'equity', 'income', 'expense')

    @api.model
    def _om_sections(self):
        return {'consolidation': self.env._("Consolidation")}

    @api.model
    def _om_name_label(self, options):
        return self.env._("Group Account")

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    @api.model
    def _ocr_periods(self):
        return self.env['om.consolidation.period'].search([('state', 'in', ('computed', 'approved'))])

    @api.model
    def _om_choices(self):
        periods = self._ocr_periods()
        choices = [[str(period.id), '%s - %s' % (period.group_id.name, period.name)] for period in periods]
        return [
            {'key': 'period_id', 'label': self.env._("Period"), 'icon': 'calendar_today', 'menu': 'bar', 'summary': False,
             'default': choices[0][0] if choices else '0',
             'choices': choices or [['0', self.env._("No computed period")]]},
            {'key': 'compare_period_id', 'label': self.env._("Compare With"), 'icon': 'swap_horiz', 'menu': 'bar',
             'default': '0', 'choices': [['0', self.env._("No comparison")]] + choices},
        ]

    @api.model
    def _om_toggles(self):
        return [
            {'key': 'hide_zero', 'label': self.env._("Hide zero lines"), 'default': True,
             'help': self.env._("Leave out the group accounts without any figure.")},
            {'key': 'company_currency', 'label': self.env._("Amounts in company currency"), 'default': False,
             'help': self.env._("A column per company with the amounts in its own currency, before translation.")},
        ]

    @api.model
    def _ocr_period(self, options, key='period_id'):
        value = str(options.get(key) or '')
        period = self.env['om.consolidation.period'].browse(int(value) if value.isdigit() else 0).exists()
        return period if period.state in ('computed', 'approved') else period.browse()

    @api.model
    def _ocr_compare_period(self, options, period):
        compare = self._ocr_period(options, 'compare_period_id')
        return compare if compare and compare != period and compare.group_id == period.group_id else compare.browse()

    @api.model
    def _om_prepare(self, options):
        period = self._ocr_period(options)
        return self.with_context(om_consolidation_period_id=period.id)

    @api.model
    def _om_currency(self):
        period = self.env['om.consolidation.period'].browse(self.env.context.get('om_consolidation_period_id') or 0)
        return period.exists().currency_id or self.env.company.currency_id

    @api.model
    def _om_subtitle(self, options):
        period = self._ocr_period(options)
        if not period:
            return self.env._("No computed consolidation period you can open: compute a period of a group of your companies.")
        state = dict(period._fields['state']._description_selection(self.env))[period.state]
        return self.env._(
            "%(group)s, %(start)s - %(end)s, in %(currency)s (%(state)s)", group=period.group_id.name,
            start=self._om_format_date(period.date_from), end=self._om_format_date(period.date_to),
            currency=period.currency_id.name, state=state)

    @api.model
    def _om_filter_summary(self, options):
        summary = super()._om_filter_summary(options)
        period = self._ocr_period(options)
        if period:
            rates = ', '.join(self.env._(
                "%(currency)s: closing %(closing)s, average %(average)s", currency=rate.company_currency_id.name,
                closing=round(rate.closing_rate, 6), average=round(rate.average_rate, 6))
                for rate in period.rate_ids if rate.company_currency_id != period.currency_id)
            if rates:
                summary.append((self.env._("Rates"), rates))
        return summary

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    @api.model
    def _ocr_companies(self, period):
        return period.group_id.member_ids.company_id

    @api.model
    def _om_get_columns(self, options):
        period = self._ocr_period(options)
        if not period:
            return [{'key': 'total', 'label': self.env._("Group Total"), 'type': 'monetary', 'optional': False}]
        translated = self.env._("Translated (%s)", period.currency_id.name)
        columns = []
        for company in self._ocr_companies(period):
            columns.append({'key': 'c_%s' % company.id, 'label': company.name, 'type': 'monetary', 'drill': True,
                            'group': translated,
                            'help': self.env._("The balances of %(company)s translated into %(currency)s.",
                                               company=company.name, currency=period.currency_id.name)})
        if options.get('company_currency'):
            for company in self._ocr_companies(period):
                columns.append({'key': 'cc_%s' % company.id, 'label': '%s (%s)' % (company.name, company.currency_id.name),
                                'type': 'float', 'digits': company.currency_id.decimal_places, 'drill': True,
                                'group': self.env._("Company Currency"),
                                'help': self.env._("The balances of %s in its own currency.", company.name)})
        columns += [
            {'key': 'elim', 'label': self.env._("Eliminations"), 'type': 'monetary',
             'help': self.env._("Inter-company balances, sales and purchases and dividends removed, and the "
                                "differences between the books of the companies.")},
            {'key': 'adj', 'label': self.env._("Adjustments"), 'type': 'monetary',
             'help': self.env._("The manual adjustments of the period.")},
            {'key': 'total', 'label': self.env._("Group Total"), 'type': 'monetary', 'optional': False},
        ]
        compare = self._ocr_compare_period(options, period)
        if compare:
            columns += [
                {'key': 'total_cmp', 'label': self.env._("Group Total (%s)", compare.name), 'type': 'monetary'},
                {'key': 'delta', 'label': self.env._("Change"), 'type': 'monetary'},
            ]
        return columns

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _ocr_figures(self, period):
        """{group account: {'values': {column: amount}, 'children': [(key, label, values, drill)]}} of a
        period, as booked (debit positive)."""
        figures = defaultdict(lambda: {'values': defaultdict(float), 'children': {}})
        for line in period.line_ids:
            entry = figures[line.group_account_id]
            if line.kind in ('balance', 'translation'):
                column = 'c_%s' % line.company_id.id
                values = {column: line.translated, 'total': line.translated}
                if line.kind == 'balance':
                    values['cc_%s' % line.company_id.id] = line.amount
                child_key = ('company', line.company_id.id, line.account_id.id or 0, line.kind)
            else:
                values = {'elim': line.translated, 'total': line.translated}
                child_key = ('elim', line.id)
            for key, value in values.items():
                entry['values'][key] += value
            child = entry['children'].setdefault(child_key, {'name': line._om_label(), 'values': defaultdict(float),
                                                             'line': line})
            for key, value in values.items():
                child['values'][key] += value
        for adjustment_line in self.env['om.consolidation.adjustment.line'].search([('period_id', '=', period.id)]):
            amount = adjustment_line.debit - adjustment_line.credit
            entry = figures[adjustment_line.group_account_id]
            entry['values']['adj'] += amount
            entry['values']['total'] += amount
            name = adjustment_line.adjustment_id.name
            if adjustment_line.name:
                name = '%s - %s' % (name, adjustment_line.name)
            if adjustment_line.company_id:
                name = '%s (%s)' % (name, adjustment_line.company_id.name)
            entry['children'][('adj', adjustment_line.id)] = {
                'name': self.env._("Adjustment: %s", name), 'values': {'adj': amount, 'total': amount},
                'line': False, 'adjustment': adjustment_line.adjustment_id}
        return figures

    @api.model
    def _ocr_account_values(self, figures, account, sign):
        if account not in figures:
            return {}
        # a company without a figure shows a blank, not a zero
        return {key: value * sign for key, value in figures[account]['values'].items()
                if key == 'total' or abs(value) >= 0.005}

    @api.model
    def _ocr_children(self, period, figures, account, sign, parent_id, level):
        lines = []
        if account not in figures:
            return lines
        order = {company.id: index for index, company in enumerate(self._ocr_companies(period))}

        def sort_key(item):
            key, child = item
            return (key[0] != 'company', order.get(key[1], 0) if key[0] == 'company' else 0, child['name'])

        for key, child in sorted(figures[account]['children'].items(), key=sort_key):
            if all(abs(value) < 0.005 for value in child['values'].values()):
                continue
            line_id = '%s|%s' % (parent_id, '-'.join(str(part) for part in key))
            record = child.get('line')
            drill = bool(record and record.kind == 'balance')
            extra = {}
            if child.get('adjustment'):
                extra['open'] = {'res_model': 'om.consolidation.adjustment', 'res_id': child['adjustment'].id}
            line = self._om_line(line_id, child['name'], {k: v * sign for k, v in child['values'].items()},
                                 parent_id=parent_id, level=level, kind='detail', drill=drill)
            line.update(extra)
            lines.append({'id': line_id, 'name': child['name'], 'line': line, 'children': []})
        return lines

    @api.model
    def _ocr_account_node(self, period, figures, compare_figures, account, sign, options, parent_id, level):
        line_id = '%s|gacc-%s' % (parent_id, account.id) if parent_id else 'gacc-%s' % account.id
        values = self._ocr_account_values(figures, account, sign)
        if compare_figures is not None:
            values['total_cmp'] = self._ocr_account_values(compare_figures, account, sign).get('total', 0.0)
            values['delta'] = values.get('total', 0.0) - values['total_cmp']
        children = self._ocr_children(period, figures, account, sign, line_id, level + 1)
        line = self._om_line(line_id, account.display_name, values, parent_id=parent_id, level=level,
                             kind='leaf', has_children=bool(children), drill=True)
        return {'id': line_id, 'name': account.display_name, 'line': line, 'children': children}

    @api.model
    def _ocr_shown(self, node, options, currency):
        if not options.get('hide_zero'):
            return True
        return any(not currency.is_zero(value or 0.0) for value in node['line']['values'].values())

    @api.model
    def _ocr_sum(self, nodes):
        total = defaultdict(float)
        for node in nodes:
            for key, value in node['line']['values'].items():
                total[key] += value or 0.0
        return dict(total)

    @api.model
    def _ocr_section(self, key, name, nodes, parent_id=False, level=0, values=None):
        line_id = '%s|%s' % (parent_id, key) if parent_id else key
        for node in nodes:
            self._ocr_reparent(node, line_id, level + 1)
        line = self._om_line(line_id, name, values if values is not None else self._ocr_sum(nodes),
                             parent_id=parent_id, level=level, kind='group', has_children=bool(nodes),
                             count=len(nodes), unfolded=True)
        return {'id': line_id, 'name': name, 'line': line, 'children': nodes}

    @api.model
    def _ocr_reparent(self, node, parent_id, level):
        """Move a node and its children under ``parent_id``: the ids start with the id of their parent."""
        own = node['id'].rpartition('|')[2]
        new_id = '%s|%s' % (parent_id, own)
        node['id'] = new_id
        node['line'].update(id=new_id, parent_id=parent_id, level=level)
        for child in node['children']:
            self._ocr_reparent(child, new_id, level + 1)

    @api.model
    def _ocr_accounts(self, period, kinds):
        return period.group_id.account_ids.filtered(lambda account: account.kind in kinds)

    @api.model
    def _ocr_account_nodes(self, period, figures, compare_figures, kinds, options, sign=None):
        currency = period.currency_id
        nodes = []
        for account in self._ocr_accounts(period, kinds):
            node = self._ocr_account_node(period, figures, compare_figures, account,
                                          sign if sign is not None else SIGNS[account.kind], options, False, 0)
            if self._ocr_shown(node, options, currency):
                nodes.append(node)
        return nodes

    @api.model
    def _om_compute(self, options):
        period = self._ocr_period(options)
        if not period:
            return {'tree': [], 'total': False, 'period_id': False}
        period.group_id._om_check_member_access()
        figures = self._ocr_figures(period)
        compare = self._ocr_compare_period(options, period)
        compare_figures = self._ocr_figures(compare) if compare else None
        tree, total = self._ocr_tree(period, figures, compare_figures, options)
        if options['search']:
            tree = self._om_search_tree(tree, options['search'])
        # the computed report is kept between requests: no records in it
        return {'tree': tree, 'total': total, 'period_id': period.id}

    @api.model
    def _ocr_tree(self, period, figures, compare_figures, options):
        return [], False

    @api.model
    def _om_lines(self, data, options, parent_id=False, offset=0, limit=PAGE_SIZE):
        if not parent_id:
            nodes = data['tree']
        else:
            node = self._om_find_node(data['tree'], parent_id)
            if not node:
                return [], 0
            nodes = node['children']
        page, more = self._om_page(nodes, offset, limit)
        return [node['line'] for node in page], more

    @api.model
    def _om_total(self, data, options):
        if not data.get('total'):
            return False
        return self._om_line('total', self._ocr_total_label(), data['total'], kind='total')

    @api.model
    def _ocr_total_label(self):
        return self.env._("Total")

    @api.model
    def _om_get_kpis(self, data, options):
        period = self.env['om.consolidation.period'].browse(data.get('period_id') or [])
        if not period:
            return []
        return [
            {'key': 'companies', 'label': self.env._("Companies"), 'value': len(period.group_id.member_ids),
             'type': 'int', 'icon': 'business'},
            {'key': 'differences', 'label': self.env._("Pairs with a difference"), 'value': period.difference_count,
             'type': 'int', 'icon': 'warning', 'tone': 'danger' if period.difference_count else 'success'},
            {'key': 'difference', 'label': self.env._("Elimination differences"), 'value': period.difference_amount,
             'type': 'monetary', 'icon': 'balance', 'tone': 'danger' if period.difference_count else 'success'},
        ]

    # ------------------------------------------------------------------
    # Journal items behind a figure
    # ------------------------------------------------------------------

    @api.model
    def _ocr_line_part(self, line_id, prefix):
        for part in reversed((line_id or '').split('|')):
            key, _sep, value = part.partition('-')
            if key == prefix:
                return value
        return False

    @api.model
    def _ocr_items_action(self, period, companies, line_id):
        """The journal items behind a line, in the currency of each company: of the company account of
        a detail line, or of the accounts of ``companies`` mapped to the group account of a line."""
        group = period.group_id
        group._om_check_member_access()
        detail = self._ocr_line_part(line_id, 'company')
        group_account_id = self._ocr_line_part(line_id, 'gacc')
        Account = self.env['account.account']
        domains = []
        if detail:
            company_id, account_id, kind = (detail.split('-') + ['0', '0', ''])[:3]
            if kind != 'balance' or not company_id.isdigit() or not account_id.isdigit():
                return False
            companies = self.env['res.company'].browse(int(company_id))
            accounts = Account.browse(int(account_id)) if int(account_id) else Account
            domains.append(period._om_items_domain(companies, accounts, earlier=not int(account_id)))
        elif group_account_id and group_account_id.isdigit():
            group_account = self.env['om.consolidation.account'].browse(int(group_account_id))
            for company in companies:
                mapping = group._om_account_map(company)
                accounts = Account.browse([account_id for account_id, mapped in mapping.items() if mapped == group_account])
                domains.append(period._om_items_domain(
                    company, accounts, earlier=group_account == group.retained_earnings_account_id))
        domains = [domain for domain in domains if domain]
        if not domains:
            return False
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_account_moves_all')
        if len(companies) == 1:
            name = self.env._("%(company)s - Journal Items (%(currency)s)", company=companies.name,
                              currency=companies.currency_id.name)
        else:
            name = self.env._("Journal Items (in the currency of each company)")
        action.update({
            'name': name,
            'display_name': name,
            'domain': list(Domain.OR(domains)),
            'context': {'create': False, 'search_default_group_by_move': 0, 'search_default_posted': 0,
                        'allowed_company_ids': list(dict.fromkeys(self.env.companies.ids + companies.ids))},
            'target': 'current',
        })
        action.pop('path', None)
        return action

    @api.model
    def _om_line_action(self, options, line_id):
        period = self._ocr_period(options)
        if not period:
            return False
        detail = self._ocr_line_part(line_id, 'company')
        if detail:
            company_id = detail.split('-')[0]
            companies = self.env['res.company'].browse(int(company_id) if company_id.isdigit() else [])
        else:
            companies = self._ocr_companies(period)
        return self._ocr_items_action(period, companies, line_id)

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        period = self._ocr_period(options)
        if not period:
            return False
        company_id = column_key.rpartition('_')[2]
        if not company_id.isdigit():
            return False
        company = self.env['res.company'].browse(int(company_id))
        if company not in self._ocr_companies(period):
            return False
        detail = self._ocr_line_part(line_id, 'company')
        if detail and detail.split('-')[0] != company_id:
            return False
        return self._ocr_items_action(period, company, line_id)


class OmConsolidationTrialBalance(models.AbstractModel):
    _name = 'om.consolidation.trial.balance'
    _inherit = 'om.consolidation.report'
    _description = 'Consolidated Trial Balance'

    _report_name = 'Consolidated Trial Balance'
    _report_description = _lt("Every group account, with a column per company, the eliminations and the group total.")
    _report_sequence = 110
    _report_icon = 'balance'

    @api.model
    def _om_report_title(self):
        return self.env._("Consolidated Trial Balance")

    @api.model
    def _ocr_tree(self, period, figures, compare_figures, options):
        nodes = self._ocr_account_nodes(period, figures, compare_figures, self._ocr_kinds, options, sign=1)
        if not nodes:
            return [], False
        return nodes, self._ocr_sum(nodes)


class OmConsolidationProfitLoss(models.AbstractModel):
    _name = 'om.consolidation.profit.loss'
    _inherit = 'om.consolidation.report'
    _description = 'Consolidated Profit and Loss'

    _report_name = 'Consolidated Profit and Loss'
    _report_description = _lt("Income and expense of the group, translated at the average rate, after eliminations.")
    _report_sequence = 111
    _report_icon = 'show_chart'
    _ocr_kinds = ('income', 'expense')

    @api.model
    def _om_report_title(self):
        return self.env._("Consolidated Profit and Loss")

    @api.model
    def _ocr_total_label(self):
        return self.env._("Net Profit")

    @api.model
    def _ocr_tree(self, period, figures, compare_figures, options):
        income = self._ocr_account_nodes(period, figures, compare_figures, ('income',), options)
        expense = self._ocr_account_nodes(period, figures, compare_figures, ('expense',), options)
        if not income and not expense:
            return [], False
        income_total, expense_total = self._ocr_sum(income), self._ocr_sum(expense)
        tree = [self._ocr_section('income', self.env._("Income"), income, values=income_total),
                self._ocr_section('expense', self.env._("Expenses"), expense, values=expense_total)]
        keys = set(income_total) | set(expense_total)
        return tree, {key: income_total.get(key, 0.0) - expense_total.get(key, 0.0) for key in keys}


class OmConsolidationBalanceSheet(models.AbstractModel):
    _name = 'om.consolidation.balance.sheet'
    _inherit = 'om.consolidation.report'
    _description = 'Consolidated Balance Sheet'

    _report_name = 'Consolidated Balance Sheet'
    _report_description = _lt("Assets, liabilities and equity of the group at the end of the period, with the "
                              "translation reserve and the result of the period.")
    _report_sequence = 112
    _report_icon = 'account_balance'

    @api.model
    def _om_report_title(self):
        return self.env._("Consolidated Balance Sheet")

    @api.model
    def _ocr_total_label(self):
        return self.env._("Liabilities and Equity")

    @api.model
    def _ocr_tree(self, period, figures, compare_figures, options):
        assets = self._ocr_account_nodes(period, figures, compare_figures, ('asset',), options)
        liabilities = self._ocr_account_nodes(period, figures, compare_figures, ('liability',), options)
        equity = self._ocr_account_nodes(period, figures, compare_figures, ('equity',), options)
        # the result of the period, in the equity until it is carried to the retained earnings
        result = defaultdict(float)
        for account in self._ocr_accounts(period, ('income', 'expense')):
            for key, value in self._ocr_account_values(figures, account, -1).items():
                result[key] += value
        if compare_figures is not None:
            for account in self._ocr_accounts(period, ('income', 'expense')):
                result['total_cmp'] += self._ocr_account_values(compare_figures, account, -1).get('total', 0.0)
            result['delta'] = result['total'] - result['total_cmp']
        if any(not period.currency_id.is_zero(value) for value in result.values()):
            name = self.env._("Result of the Period")
            equity.append({'id': 'result', 'name': name, 'children': [], 'line': self._om_line(
                'result', name, dict(result), kind='leaf',
                help=self.env._("The income less the expense of the period, from the consolidated profit and loss."))})
        if not assets and not liabilities and not equity:
            return [], False
        liabilities_total, equity_total = self._ocr_sum(liabilities), self._ocr_sum(equity)
        keys = set(liabilities_total) | set(equity_total)
        both = {key: liabilities_total.get(key, 0.0) + equity_total.get(key, 0.0) for key in keys}
        tree = [
            self._ocr_section('assets', self.env._("Assets"), assets),
            self._ocr_section('liabilities', self.env._("Liabilities"), liabilities, values=liabilities_total),
            self._ocr_section('equity', self.env._("Equity"), equity, values=equity_total),
        ]
        return tree, both
