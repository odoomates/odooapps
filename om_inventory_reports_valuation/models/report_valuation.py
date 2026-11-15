from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmInventoryReportValuation(models.AbstractModel):
    """The value of the stock on a date: quantity, unit cost and value, by
    category, product, warehouse, location or lot."""
    _name = 'om.inventory.report.valuation'
    _inherit = 'om.inventory.report.stock_on_hand'
    _description = 'Stock Valuation Report'

    _report_key = 'valuation'
    _report_name = _lt('Stock Valuation')
    _report_section = 'valuation'
    _report_sequence = 12
    _report_icon = 'payments'
    _report_description = _lt('Quantity, unit cost and value of the stock on any date.')
    _report_group_by = ('category', 'product', 'warehouse', 'location', 'lot', 'owner')
    _report_default_group_by = ('category', 'product')
    _report_has_details = False
    _report_compare_keys = ('quantity', 'value')
    _report_bar_column = 'value'

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'quantity', 'label': self.env._("Quantity"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
            {'key': 'unit_cost', 'label': self.env._("Unit Cost"), 'type': 'monetary'},
            {'key': 'value', 'label': self.env._("Value"), 'type': 'monetary', 'aggregate': 'sum', 'optional': False},
            {'key': 'share', 'label': self.env._("Share of Value"), 'type': 'percent', 'aggregate': 'sum'},
            {'key': 'cost_method', 'label': self.env._("Costing Method"), 'type': 'char', 'visible': False},
        ]

    @api.model
    def _om_normalize_options(self, options):
        options = super()._om_normalize_options(options)
        options['group_by'] = [g for g in options['group_by'] if g != 'package'] or ['product']
        return options

    @api.model
    def _om_has_details(self, options):
        return False

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        start, end = self._om_period_bounds(options)
        self._om_set_values(rows, end, [('quantity', 'value')], options)
        total = sum(r['value'] for r in rows) or 1.0
        methods = dict(self.env['product.category']._fields['property_cost_method']._description_selection(self.env))
        products = self.env['product.product'].with_context(active_test=False).browse({r['product_id'] for r in rows})
        method_by_product = {p.id: methods.get(p.cost_method, '') for p in products}
        for row in rows:
            row['share'] = row['value'] / total * 100
            row['cost_method'] = method_by_product.get(row['product_id'], '')
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        self._om_unit_cost_node(node, 'quantity', 'value')
        methods = {r.get('cost_method') for r in node['rows']}
        node['values']['cost_method'] = methods.pop() if len(methods) == 1 else ''

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['rows']
        total = data['total']['values'].get('value', 0.0)
        products = {r['product_id'] for r in rows if r.get('quantity')}
        negative = [r for r in data['all_rows'] if (r.get('value') or 0) < 0]
        by_category = {}
        for row in rows:
            by_category[row.get('category_id')] = by_category.get(row.get('category_id'), 0.0) + row['value']
        top = max(by_category.items(), key=lambda item: item[1], default=(False, 0.0))
        top_name = self._om_names('category', [top[0]]).get(top[0], '') if top[0] else ''
        return [
            {'key': 'value', 'label': self.env._("Stock value"), 'value': total, 'type': 'monetary',
             'icon': 'payments'},
            {'key': 'products', 'label': self.env._("Products valued"), 'value': len(products), 'type': 'int',
             'icon': 'package_2'},
            {'key': 'average', 'label': self.env._("Average per product"),
             'value': total / len(products) if products else 0.0, 'type': 'monetary', 'icon': 'calculate'},
            {'key': 'top', 'label': self.env._("Largest category: %s", top_name) if top_name else
             self.env._("Largest category"),
             'value': top[1] / total * 100 if total else 0.0, 'type': 'percent', 'icon': 'pie_chart'},
            {'key': 'negative', 'label': self.env._("Negative values"), 'value': len(negative), 'type': 'int',
             'icon': 'warning', 'tone': 'danger' if negative else 'success', 'filter': 'negative'},
        ]
