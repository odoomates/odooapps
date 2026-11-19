import ast

from odoo import api, models
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

from odoo.addons.accounting_pdf_reports.report.report_tax_grid import _Evaluator

_lt = LazyTranslate(__name__)

# the figure types of the tax returns, as the column types of the engine
FIGURE_TYPES = {'monetary': 'monetary', 'percentage': 'percent', 'integer': 'int', 'float': 'float'}


class OmDynamicReportTaxGrid(models.AbstractModel):
    """Tax Return: the tax return of the country as its localization lays it
    out, grid by grid, with the totals of the grids; a grid opens the journal
    items it adds up. The figures are those of the PDF Tax Report by Tax Grid.
    """
    _name = 'om.dynamic.report.tax.grid'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Tax Return'

    _report_name = 'Tax Return'
    _report_description = _lt("The tax return of your country, grid by grid.")
    _report_section = 'statements'
    _report_sequence = 6
    _report_icon = 'fact_check'
    _report_compare = True

    @api.model
    def _om_report_title(self):
        return self.env._("Tax Return")

    @api.model
    def _odr_tax_returns(self):
        """The tax returns of the localizations installed, those of the country of the company first."""
        generic = self.env.ref('account.generic_tax_report', raise_if_not_found=False)
        if not generic:
            return self.env['account.report']
        returns = self.env['account.report'].search([
            ('root_report_id', '=', generic.id), ('country_id', '!=', False), ('section_main_report_ids', '=', False),
        ])
        country = self.env.company.account_fiscal_country_id
        return returns.sorted(lambda report: (report.country_id != country, report.name))


    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids')

    @api.model
    def _om_choices(self):
        returns = self._odr_tax_returns()
        choices = [self._odr_target_move_choice()]
        if returns:
            choices.insert(0, {'key': 'tax_return', 'label': self.env._("Tax Return"), 'icon': 'fact_check',
                               'menu': 'bar', 'default': str(returns[0].id),
                               'choices': [[str(report.id), report.display_name] for report in returns]})
        return choices

    @api.model
    def _odr_tax_return(self, options):
        value = str(options.get('tax_return') or '')
        report = self.env['account.report'].browse(int(value)).exists() if value.isdigit() else False
        return report if report and report in self._odr_tax_returns() else self._odr_tax_returns()[:1]

    @api.model
    def _odr_columns_of(self, report):
        return [{'label': column.expression_label, 'name': column.name, 'type': column.figure_type}
                for column in report.column_ids] or [{'label': 'balance', 'name': self.env._("Balance"),
                                                      'type': 'monetary'}]

    @api.model
    def _om_get_columns(self, options):
        report = self._odr_tax_return(options)
        if not report:
            return []
        report_columns = self._odr_columns_of(report)
        periods = self._odr_period_options(options)
        compared = len(periods) > 1
        columns = []
        for index, period in enumerate(periods):
            suffix = '_%s' % index if index else ''
            # compared, the columns of the return repeat under each period
            group = self._om_period_label(period) if compared else False
            columns += [{'key': 'c_%s%s' % (column['label'], suffix), 'label': column['name'], 'group': group,
                         'type': FIGURE_TYPES.get(column['type'], 'monetary'), 'drill': True}
                        for column in report_columns]
        if self._odr_variation_column(report_columns, periods):
            columns.append({'key': 'variation', 'label': self.env._("Variation %"), 'type': 'percent',
                            'help': self.env._("Change from the compared period to this one.")})
        return columns

    @api.model
    def _odr_variation_column(self, report_columns, periods):
        """The column of the variation compares the amounts of a return of one amount column with one period."""
        return (len(periods) == 2 and len(report_columns) == 1
                and FIGURE_TYPES.get(report_columns[0]['type'], 'monetary') == 'monetary')

    @api.model
    def _odr_evaluator(self, options, report):
        return _Evaluator(self.env, report, {
            'date_from': options['date_from'], 'date_to': options['date_to'],
            'target_move': options.get('target_move', 'posted'),
            'used_context': {'company_id': self.env.company.id, 'journal_ids': options.get('journal_ids') or []},
        })

    @api.model
    def _odr_tree(self, options):
        report = self._odr_tax_return(options)
        if not report:
            return [], False
        # the journal items are read from the database: write the pending changes first
        self.env.flush_all()
        periods = self._odr_period_options(options)
        evaluators = [self._odr_evaluator(period, report) for period in periods]
        columns = self._odr_columns_of(report)
        variation = self._odr_variation_column(columns, periods)

        def build(report_line, parent_id, level):
            node_id = '%s|line-%s' % (parent_id, report_line.id) if parent_id else 'line-%s' % report_line.id
            expressions = {expression.label: expression for expression in report_line.expression_ids}
            values = {}
            for index, evaluator in enumerate(evaluators):
                suffix = '_%s' % index if index else ''
                for column in columns:
                    expression = expressions.get(column['label'])
                    value = evaluator.value(expression) if expression else None
                    if expression and expression.blank_if_zero and not value:
                        value = None
                    elif isinstance(value, float) and not value:
                        value = 0.0  # not -0.0
                    values['c_%s%s' % (column['label'], suffix)] = value if value is not None else False
            if variation:
                key = 'c_%s' % columns[0]['label']
                current, previous = values.get(key), values.get(key + '_1')
                values['variation'] = ((current or 0.0) - previous) / abs(previous) * 100 \
                    if isinstance(previous, float) and previous else False
            children = [build(child, node_id, level + 1)
                        for child in report_line.children_ids.sorted(lambda line: (line.sequence, line.id))]
            name = report_line.name
            drill = any(expression.engine in ('tax_tags', 'domain') for expression in report_line.expression_ids)
            line = self._om_line(node_id, name, values, parent_id=parent_id, level=level,
                                 kind='group' if children else 'leaf', has_children=bool(children),
                                 count=len(children), unfolded=True, drill=drill)
            return self._odr_node(node_id, name, line, children)

        roots = report.line_ids.filtered(lambda line: not line.parent_id).sorted(lambda line: (line.sequence, line.id))
        return [build(line, False, 0) for line in roots], False

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        """The journal items of a grid: those with its tax tags, or those of its domain."""
        report = self._odr_tax_return(options)
        line_part = line_id.rsplit('|', 1)[-1]
        # a compared column ends with the rank of its period: 'c_balance_1'
        column_key, period = self._odr_cell_scope(options, column_key)
        if not report or not line_part.startswith('line-') or not column_key.startswith('c_'):
            return False
        report_line = self.env['account.report.line'].browse(int(line_part[5:])).exists()
        expression = report_line.expression_ids.filtered(lambda expression: expression.label == column_key[2:])[:1]
        if not expression or expression.engine not in ('tax_tags', 'domain'):
            return False
        evaluator = self._odr_evaluator(period, report)
        domain = evaluator._domain(expression.date_scope)
        if expression.engine == 'tax_tags':
            country = (report.country_id or self.env.company.account_fiscal_country_id).id
            tags = self.env['account.account.tag']._get_tax_tags(expression.formula, country)
            domain &= Domain('tax_tag_ids', 'in', tags.ids)
        else:
            domain &= Domain(ast.literal_eval(expression.formula))
        return self._odr_journal_items_action(list(domain), report_line.name)
