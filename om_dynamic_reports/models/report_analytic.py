from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

# the dimensions of the report and the field of the analytic line they group on
DIMENSION_FIELDS = {
    'partner': 'partner_id',
    'account': 'general_account_id',
    'product': 'product_id',
    'journal': 'journal_id',
}
DETAIL_LIMIT = 2000


class OmDynamicReportAnalytic(models.AbstractModel):
    """Analytic Report: income, expense and balance of the analytic lines,
    grouped as the user likes (analytic account, partner, account, product,
    journal); the last level unfolds into the analytic lines.

    It is a report of the simple kind: it gives rows and the engine groups
    them, sums them, sorts and searches them."""
    _name = 'om.dynamic.report.analytic'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Analytic Report'

    _report_name = 'Analytic Report'
    _report_description = _lt("Income and expense by analytic account, partner, account or product.")
    _report_section = 'ledgers'
    _report_sequence = 40
    _report_icon = 'donut_small'
    _report_group_by = ('analytic_account', 'partner', 'account', 'product', 'journal')
    _report_default_group_by = ('analytic_account', 'partner')
    _report_has_details = True

    @api.model
    def _om_report_title(self):
        return self.env._("Analytic Report")

    @api.model
    def _om_report_available(self):
        return self.env.user.has_group('analytic.group_analytic_accounting')

    @api.model
    def _om_dimensions(self):
        return {
            'analytic_account': {'label': self.env._("Analytic Account"), 'model': 'account.analytic.account',
                                 'icon': 'donut_small'},
            'partner': {'label': self.env._("Partner"), 'model': 'res.partner', 'icon': 'person'},
            'account': {'label': self.env._("Account"), 'model': 'account.account', 'icon': 'account_tree'},
            'product': {'label': self.env._("Product"), 'model': 'product.product', 'icon': 'package_2'},
            'journal': {'label': self.env._("Journal"), 'model': 'account.journal', 'icon': 'book'},
        }

    @api.model
    def _om_empty_name(self, dim):
        return {
            'partner': self.env._("No partner"),
            'account': self.env._("No account"),
            'product': self.env._("No product"),
            'journal': self.env._("No journal"),
        }.get(dim, super()._om_empty_name(dim))

    @api.model
    def _om_filters(self):
        return [
            {'key': 'analytic_account_ids', 'label': self.env._("Analytic Accounts"),
             'model': 'account.analytic.account', 'icon': 'donut_small', 'domain': []},
            *self._odr_filters('partner_ids', 'account_ids', 'journal_ids'),
        ]

    @api.model
    def _om_choices(self):
        project_plan, other_plans = self.env['account.analytic.plan']._get_all_plans()
        plans = project_plan + other_plans
        return [{'key': 'analytic_plan', 'label': self.env._("Analytic Plan"), 'icon': 'category', 'menu': 'bar',
                 'default': str(project_plan.id) if project_plan else '0',
                 'choices': [(str(plan.id), plan.name) for plan in plans] or [('0', self.env._("No plan"))]}]

    @api.model
    def _odr_plan_column(self, options):
        """The field of the analytic line holding the accounts of the chosen plan."""
        plan = self.env['account.analytic.plan'].browse(int(options['analytic_plan'] or 0)).exists()
        return plan._column_name() if plan else 'account_id'

    @api.model
    def _om_toggles(self):
        return [{'key': 'hide_zero', 'label': self.env._("Hide zero lines"), 'default': True}]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': self.env._("Date"), 'type': 'date', 'detail_only': True},
            {'key': 'label', 'label': self.env._("Label"), 'type': 'char', 'detail_only': True},
            {'key': 'quantity', 'label': self.env._("Quantity"), 'type': 'float', 'aggregate': 'sum',
             'visible': False},
            {'key': 'income', 'label': self.env._("Income"), 'type': 'monetary', 'aggregate': 'sum',
             'blank_zero': True},
            {'key': 'expense', 'label': self.env._("Expense"), 'type': 'monetary', 'aggregate': 'sum',
             'blank_zero': True},
            {'key': 'balance', 'label': self.env._("Balance"), 'type': 'monetary', 'aggregate': 'sum'},
        ]

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------

    @api.model
    def _odr_analytic_domain(self, options):
        column = self._odr_plan_column(options)
        domain = [('company_id', 'in', self._odr_company_ids() + [False]),
                  ('date', '<=', options['date_to']), (column, '!=', False)]
        if options.get('date_from'):
            domain.append(('date', '>=', options['date_from']))
        if options['analytic_account_ids']:
            domain.append((column, 'in', options['analytic_account_ids']))
        if options['partner_ids']:
            domain.append(('partner_id', 'in', options['partner_ids']))
        if options['account_ids']:
            domain.append(('general_account_id', 'in', options['account_ids']))
        if options['journal_ids']:
            domain.append(('journal_id', 'in', options['journal_ids']))
        return domain

    @api.model
    def _om_get_rows(self, options):
        Line = self.env['account.analytic.line']
        fields_by_dim = {**DIMENSION_FIELDS, 'analytic_account': self._odr_plan_column(options)}
        groupby = [fields_by_dim[dim] for dim in options['group_by']]
        domain = self._odr_analytic_domain(options)
        rows = {}
        for sign, part in ((1, [('amount', '>=', 0)]), (-1, [('amount', '<', 0)])):
            for *keys, company, amount, quantity in Line._read_group(
                    domain + part, groupby + ['company_id'], ['amount:sum', 'unit_amount:sum']):
                amount = self._odr_convert(amount, company)
                ids = tuple(key.id for key in keys)
                row = rows.setdefault(ids, {
                    **{dim + '_id': res_id for dim, res_id in zip(options['group_by'], ids)},
                    'income': 0.0, 'expense': 0.0, 'balance': 0.0, 'quantity': 0.0,
                })
                row['income' if sign > 0 else 'expense'] += abs(amount)
                row['balance'] += amount
                row['quantity'] += quantity
        return list(rows.values())

    @api.model
    def _om_detail_lines(self, node, options):
        domain = self._odr_analytic_domain(options)
        fields_by_dim = {**DIMENSION_FIELDS, 'analytic_account': self._odr_plan_column(options)}
        for part in node['id'].split('|'):
            dim, _sep, res_id = part.rpartition('-')
            if dim in fields_by_dim:
                domain.append((fields_by_dim[dim], '=', int(res_id) or False))
        lines = self.env['account.analytic.line'].search_fetch(
            domain, ['date', 'name', 'amount', 'unit_amount', 'move_line_id', 'company_id'], order='date, id',
            limit=DETAIL_LIMIT)
        return [self._om_line(
            '%s|line-%s' % (node['id'], line.id), line.move_line_id.move_name or line.name or '', {
                'date': fields.Date.to_string(line.date),
                'label': line.name or '',
                'quantity': line.unit_amount,
                'income': max(self._odr_convert(line.amount, line.company_id), 0.0),
                'expense': max(-self._odr_convert(line.amount, line.company_id), 0.0),
                'balance': self._odr_convert(line.amount, line.company_id),
            }, parent_id=node['id'], level=node['level'] + 1, kind='detail',
            open_record=('account.move', line.move_line_id.move_id.id) if line.move_line_id
            else ('account.analytic.line', line.id),
        ) for line in lines]
