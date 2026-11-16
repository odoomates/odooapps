from collections import defaultdict

from odoo import api, models, _, _lt

SECTIONS = ('sale', 'purchase', 'withholding')


class OmDynamicReportTax(models.AbstractModel):
    """Tax Report: per tax, the base it was computed on and the tax, for the
    sales, the purchases and the withholding taxes; a tax unfolds into its
    accounts. Only the tax due on the period counts: the one of a cash basis
    tax on its payment, as in the PDF Tax Report, with its signs (sales and
    purchases as positive amounts, a withholding tax as the amount withheld).
    """
    _name = 'om.dynamic.report.tax'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Tax Report'

    _report_name = 'Tax Report'
    _report_description = _lt("Base and tax of every tax, for sales, purchases and withholding.")
    _report_section = 'statements'
    _report_sequence = 5
    _report_icon = 'receipt'
    _report_compare = True

    @api.model
    def _om_report_title(self):
        return _("Tax Report")

    @api.model
    def _om_name_label(self, options):
        return _("Tax")

    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids', 'partner_ids', 'analytic_account_ids')

    @api.model
    def _om_choices(self):
        return [self._odr_target_move_choice()]

    @api.model
    def _om_get_columns(self, options):
        periods = self._odr_period_options(options)
        columns = []
        for index, period in enumerate(periods):
            suffix = '_%s' % index if index else ''
            group = self._om_period_label(period) if len(periods) > 1 else False
            columns += [
                {'key': 'base' + suffix, 'label': _("Base"), 'type': 'monetary', 'group': group,
                 'drill': True, 'help': _("The amounts the tax was computed on.")},
                {'key': 'tax' + suffix, 'label': _("Tax"), 'type': 'monetary', 'group': group,
                 'drill': True},
            ]
        return columns

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_taxes(self):
        """{tax id: (section, sign of the base, sign of the tax)}: the taxes of the report, a group of
        taxes by its children, as the PDF report lists them."""
        is_withholding = 'is_withholding_tax_on_payment' in self.env['account.tax']._fields
        taxes = {}
        for tax in self.env['account.tax'].with_context(active_test=False).search([
                ('type_tax_use', '!=', 'none'), ('company_id', 'parent_of', self._odr_company_ids())]):
            withholding = is_withholding and tax.is_withholding_tax_on_payment
            # sales are credits: printed as positive figures like the purchases; a withholding tax is the
            # opposite of its base, the amount withheld printed as a positive figure
            base_sign = -1 if tax.type_tax_use == 'sale' else 1
            tax_sign = -base_sign if withholding else base_sign
            section = 'withholding' if withholding else tax.type_tax_use
            members = tax.children_tax_ids.filtered(lambda t: t.type_tax_use == 'none') \
                if tax.children_tax_ids else tax
            for member in members:
                taxes[member.id] = (section, base_sign, tax_sign)
        return taxes

    @api.model
    def _odr_tax_domain(self, options):
        return (self._odr_domain(options) + self._odr_period_domain(options)
                + list(self.env['account.move.line']._get_tax_exigible_domain()))

    @api.model
    def _odr_grouped(self, domain, groupby):
        """{(tax id, account id): balance} of the items of ``domain``, converted as flows."""
        result = defaultdict(float)
        converts = self._odr_converts()
        groupbys = [groupby, 'account_id'] + (['company_id', 'date:month'] if converts else [])
        for row in self._om_read_group(self.env['account.move.line'], domain, groupbys, ['balance:sum']):
            tax, account, balance = row[0], row[1], row[-1]
            if converts:
                balance = self._odr_convert_flow(balance, row[2], row[3])
            result[(tax.id, account.id)] += balance
        return result

    @api.model
    def _odr_period_figures(self, options, taxes):
        """{(tax id, account id): {'base', 'tax'}} of one period, signed for the report."""
        domain = self._odr_tax_domain(options)
        figures = defaultdict(lambda: {'base': 0.0, 'tax': 0.0})
        withholding = {tax_id for tax_id, spec in taxes.items() if spec[0] == 'withholding'}
        for (tax_id, account_id), balance in self._odr_grouped(domain + [('tax_ids', '!=', False)],
                                                               'tax_ids').items():
            if tax_id in taxes and tax_id not in withholding:
                figures[(tax_id, account_id)]['base'] += balance * taxes[tax_id][1]
        if withholding:
            # the base of a withholding tax is the one of the payment that withholds it: the invoice or the
            # bill only carries the tax that will be withheld
            for (tax_id, account_id), balance in self._odr_grouped(
                    domain + [('tax_ids', 'in', list(withholding)), ('move_id.move_type', '=', 'entry')],
                    'tax_ids').items():
                if tax_id in withholding:
                    figures[(tax_id, account_id)]['base'] += balance * taxes[tax_id][1]
        for (tax_id, account_id), balance in self._odr_grouped(domain + [('tax_line_id', '!=', False)],
                                                               'tax_line_id').items():
            if tax_id in taxes:
                figures[(tax_id, account_id)]['tax'] += balance * taxes[tax_id][2]
        return figures

    @api.model
    def _odr_tree(self, options):
        taxes = self._odr_taxes()
        periods = self._odr_period_options(options)
        suffixes = ['_%s' % index if index else '' for index in range(len(periods))]
        figures = [report._odr_period_figures(period, taxes) for report, period in self._odr_periods(options)]
        keys = [key + suffix for suffix in suffixes for key in ('base', 'tax')]
        by_tax = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(keys, 0.0)))
        for suffix, period_figures in zip(suffixes, figures):
            for (tax_id, account_id), amounts in period_figures.items():
                by_tax[tax_id][account_id]['base' + suffix] += amounts['base']
                by_tax[tax_id][account_id]['tax' + suffix] += amounts['tax']
        currency = self._om_currency()
        Tax = self.env['account.tax'].with_context(active_test=False)
        Account = self.env['account.account'].with_context(active_test=False)
        labels = {'sale': _("Sales"), 'purchase': _("Purchases"),
                  'withholding': _("Withholding")}
        nodes = []
        section_totals = {}
        for section in SECTIONS:
            section_id = 'section-%s' % section
            tax_nodes = []
            section_values = dict.fromkeys(keys, 0.0)
            section_taxes = Tax.browse([tax_id for tax_id in by_tax if taxes[tax_id][0] == section])
            for tax in section_taxes.sorted(lambda t: (t.sequence, t.name or '')):
                tax_id = '%s|tax-%s' % (section_id, tax.id)
                tax_values = dict.fromkeys(keys, 0.0)
                account_nodes = []
                accounts = Account.browse(list(by_tax[tax.id]))
                for account in accounts.sorted(self._odr_account_sort):
                    values = by_tax[tax.id][account.id]
                    for key in keys:
                        tax_values[key] += values[key]
                    if all(currency.is_zero(values[key]) for key in keys):
                        continue
                    account_id = '%s|account-%s' % (tax_id, account.id)
                    name = self._odr_account_name(account)
                    account_nodes.append(self._odr_node(account_id, name, self._om_line(
                        account_id, name, values, parent_id=tax_id, level=2, kind='leaf', drill=True)))
                if all(currency.is_zero(tax_values[key]) for key in keys):
                    continue
                for key in keys:
                    section_values[key] += tax_values[key]
                tax_nodes.append(self._odr_node(tax_id, tax.name, self._om_line(
                    tax_id, tax.name, tax_values, parent_id=section_id, level=1, kind='leaf',
                    has_children=bool(account_nodes), count=len(account_nodes), drill=True,
                    open_record=('account.tax', tax.id)), account_nodes))
            section_totals[section] = section_values
            if tax_nodes:
                nodes.append(self._odr_node(section_id, labels[section], self._om_line(
                    section_id, labels[section], section_values, kind='group', has_children=True,
                    count=len(tax_nodes), unfolded=True), tax_nodes))
        if not nodes:
            return [], False
        # the tax to pay: what the sales collected less what the purchases paid
        total = {}
        for suffix in suffixes:
            total['tax' + suffix] = (section_totals['sale']['tax' + suffix]
                                     - section_totals['purchase']['tax' + suffix])
        return nodes, total

    @api.model
    def _om_total(self, data, options):
        if not data.get('total'):
            return False
        return self._om_line('total', _("Net tax due (sales less purchases)"), data['total'], kind='total')

    # ------------------------------------------------------------------
    # Drill-down
    # ------------------------------------------------------------------

    @api.model
    def _odr_tax_action(self, options, line_id, figure):
        tax_id = self._odr_line_id_part(line_id, 'tax')
        if not tax_id:
            return False
        tax = self.env['account.tax'].browse(tax_id)
        domain = self._odr_tax_domain(options)
        domain.append(('tax_line_id', '=', tax_id) if figure == 'tax' else ('tax_ids', 'in', [tax_id]))
        account_id = self._odr_line_id_part(line_id, 'account')
        if account_id:
            domain.append(('account_id', '=', account_id))
        name = '%s - %s' % (tax.name, _("Tax") if figure == 'tax' else _("Base"))
        return self._odr_journal_items_action(domain, name)

    @api.model
    def _om_line_action(self, options, line_id):
        return self._odr_tax_action(options, line_id, 'base')

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        key, period = self._odr_cell_scope(options, column_key)
        return self._odr_tax_action(period, line_id, 'tax' if key == 'tax' else 'base')
