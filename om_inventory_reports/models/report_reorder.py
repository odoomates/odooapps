from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmInventoryReportReorder(models.AbstractModel):
    """The reordering rules and where each product stands against them."""
    _name = 'om.inventory.report.reorder'
    _inherit = 'om.inventory.report'
    _description = 'Reorder Report'

    _report_key = 'reorder'
    _report_name = _lt('Reorder Report')
    _report_section = 'stock'
    _report_sequence = 45
    _report_icon = 'add_shopping_cart'
    _report_description = _lt('Products below their reordering rule minimum, with what to order.')
    _report_date_mode = 'none'
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('status', 'warehouse', 'location', 'category', 'product')
    _report_default_group_by = ('status', 'product')
    _report_extra_options = {'only_below': True}
    _report_expand_default = True
    _report_bar_column = 'qty_to_order'

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['status'] = {
            'label': self.env._("Status"),
            'icon': 'add_shopping_cart',
            'selection': {
                'below': self.env._("Below minimum"),
                'ok': self.env._("Between minimum and maximum"),
                'above': self.env._("Above maximum"),
            },
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'product_min_qty', 'label': self.env._("Minimum"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'product_max_qty', 'label': self.env._("Maximum"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'qty_on_hand', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'qty_forecast', 'label': self.env._("Forecast"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'qty_to_order', 'label': self.env._("To Order"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_get_rows(self, options):
        domain = [('company_id', 'in', self.env.companies.ids)]
        if options.get('warehouse_ids'):
            domain.append(('warehouse_id', 'in', options['warehouse_ids']))
        if options.get('location_ids'):
            domain.append(('location_id', 'child_of' if options['child_locations'] else 'in',
                           options['location_ids']))
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            domain.append(('product_id', 'in', product_ids))
        rows = []
        for rule in self.env['stock.warehouse.orderpoint'].search(domain):
            if rule.qty_forecast < rule.product_min_qty:
                status = 'below'
            elif rule.product_max_qty and rule.qty_forecast > rule.product_max_qty:
                status = 'above'
            else:
                status = 'ok'
            if options.get('only_below') and status != 'below':
                continue
            rows.append({
                'orderpoint_id': rule.id,
                'product_id': rule.product_id.id,
                'location_id': rule.location_id.id,
                'warehouse_id': rule.warehouse_id.id,
                'status_id': status,
                'product_min_qty': rule.product_min_qty,
                'product_max_qty': rule.product_max_qty,
                'qty_on_hand': rule.qty_on_hand,
                'qty_forecast': rule.qty_forecast,
                'qty_to_order': rule.qty_to_order,
            })
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        if any(r['status_id'] == 'below' for r in node['rows']):
            node['values']['qty_forecast_tone'] = 'danger'

    @api.model
    def _om_node_open(self, node, options):
        if node.get('leaf') and len(node['rows']) == 1:
            return {'res_model': 'stock.warehouse.orderpoint', 'res_id': node['rows'][0]['orderpoint_id']}
        return super()._om_node_open(node, options)

    @api.model
    def _om_toggles(self, options):
        toggles = [{'key': 'only_below', 'label': self.env._("Only products below minimum")}]
        if 'location' in self._report_filters:
            toggles.append({'key': 'child_locations', 'label': self.env._("Include sub-locations")})
        return toggles

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options['kpi_filter']:
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        below = [r for r in rows if r['status_id'] == 'below']
        return [
            {'key': 'rules', 'label': self.env._("Reordering rules"), 'value': len(rows), 'type': 'int',
             'icon': 'checklist'},
            {'key': 'below', 'label': self.env._("Below minimum"), 'value': len(below), 'type': 'int',
             'icon': 'warning', 'tone': 'danger' if below else 'success', 'filter': 'below'},
            {'key': 'to_order', 'label': self.env._("Units to order"), 'value': sum(r['qty_to_order'] for r in below),
             'type': 'float', 'icon': 'add_shopping_cart'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'below':
            return [r for r in rows if r['status_id'] == 'below']
        return rows
