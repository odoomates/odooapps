from odoo import api, models
from odoo.tools.translate import LazyTranslate

from .report_slow_moving import USE_KINDS

_lt = LazyTranslate(__name__)


class OmInventoryReportAbc(models.AbstractModel):
    """ABC analysis: products ranked by what was used in the period. Class A
    makes the first share of the value (80 % by default), B the next (up to
    95 %), C the rest."""
    _name = 'om.inventory.report.abc'
    _inherit = 'om.inventory.report'
    _description = 'ABC Analysis Report'

    _report_key = 'abc'
    _report_name = _lt('ABC Analysis')
    _report_section = 'analysis'
    _report_sequence = 60
    _report_icon = 'bar_chart'
    _report_description = _lt('Products ranked by consumption value: classes A, B and C.')
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('abc_class', 'category', 'product')
    _report_default_group_by = ('abc_class', 'product')
    _report_extra_options = {'a_pct': 80, 'b_pct': 95, 'abc_by_qty': False}
    _report_bar_column = 'value'

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['abc_class'] = {
            'label': self.env._("Class"),
            'icon': 'bar_chart',
            'selection': {
                'A': self.env._("Class A"),
                'B': self.env._("Class B"),
                'C': self.env._("Class C"),
            },
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'issued', 'label': self.env._("Quantity Used"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("Delivered to customers and consumed in production during the period.")},
            {'key': 'unit_cost', 'label': self.env._("Unit Cost"), 'type': 'monetary', 'visible': False},
            {'key': 'value', 'label': self.env._("Consumption Value"), 'type': 'monetary', 'aggregate': 'sum',
             'optional': False},
            {'key': 'share', 'label': self.env._("Share"), 'type': 'percent', 'aggregate': 'sum'},
            {'key': 'cumulative', 'label': self.env._("Cumulative"), 'type': 'percent'},
            {'key': 'closing', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum',
             'visible': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_row_dimensions(self, options):
        return {'product'}

    @api.model
    def _om_count_internal(self, options):
        return False

    @api.model
    def _om_abc_costs(self, product_ids, options):
        """Unit cost of each product, for the consumption value."""
        products = self.env['product.product'].with_context(active_test=False).browse(product_ids)
        return {p.id: p.standard_price for p in products}

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        rows = self._om_move_balances(options, start, end)
        costs = self._om_abc_costs([r['product_id'] for r in rows], options)
        by_qty = options.get('abc_by_qty')
        for row in rows:
            row['issued'] = sum(row[k] for k in USE_KINDS)
            row['unit_cost'] = costs.get(row['product_id'], 0.0)
            row['value'] = row['issued'] * row['unit_cost']
        rows = [r for r in rows if r['issued'] > 0]
        basis = 'issued' if by_qty else 'value'
        total = sum(r[basis] for r in rows) or 1.0
        a_pct = float(options.get('a_pct') or 80)
        b_pct = max(float(options.get('b_pct') or 95), a_pct)
        cumulative = 0.0
        for row in sorted(rows, key=lambda r: -r[basis]):
            row['share'] = row[basis] / total * 100
            # a product is in the class where its share starts
            row['abc_class_id'] = 'A' if cumulative < a_pct else 'B' if cumulative < b_pct else 'C'
            cumulative += row['share']
            row['cumulative'] = cumulative
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        rows = node['rows']
        # where the group ends in the ranking: meaningful for a product or a class
        if len(rows) == 1 or node.get('dim') == 'abc_class':
            node['values']['cumulative'] = max((r['cumulative'] for r in rows), default=0.0)
        if len(rows) == 1:
            node['values']['unit_cost'] = rows[0]['unit_cost']

    @api.model
    def _om_toggles(self, options):
        return [{'key': 'abc_by_qty', 'label': self.env._("Rank by quantity instead of value")}]

    @api.model
    def _om_extra_options_meta(self, options):
        return [
            {'key': 'a_pct', 'label': self.env._("Class A up to (%)"), 'min': 1, 'step': 1},
            {'key': 'b_pct', 'label': self.env._("Class B up to (%)"), 'min': 1, 'step': 1},
        ]

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        kpis = [{'key': 'value', 'label': self.env._("Consumption value"),
                 'value': sum(r['value'] for r in rows), 'type': 'monetary', 'icon': 'payments'}]
        tones = {'A': 'success', 'B': 'info', 'C': 'warning'}
        for abc_class in ('A', 'B', 'C'):
            members = [r for r in rows if r['abc_class_id'] == abc_class]
            kpis.append({
                'key': abc_class,
                'label': self.env._("Class %(class)s: %(share).0f %% of value", **{
                    'class': abc_class, 'share': sum(r['share'] for r in members)}),
                'value': len(members), 'type': 'int', 'icon': 'bar_chart', 'tone': tones[abc_class],
                'filter': abc_class,
            })
        return kpis

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi in ('A', 'B', 'C'):
            return [r for r in rows if r['abc_class_id'] == kpi]
        return rows
