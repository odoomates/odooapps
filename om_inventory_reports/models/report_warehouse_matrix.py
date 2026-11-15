from collections import defaultdict

from odoo import api, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)


class OmInventoryReportWarehouseMatrix(models.AbstractModel):
    """Products down, warehouses across: where the stock is."""
    _name = 'om.inventory.report.warehouse_matrix'
    _inherit = 'om.inventory.report'
    _description = 'Stock by Warehouse Report'

    _report_key = 'warehouse_matrix'
    _report_name = _lt('Stock by Warehouse')
    _report_section = 'stock'
    _report_sequence = 15
    _report_icon = 'grid_view'
    _report_description = _lt('One column per warehouse: compare stock levels side by side.')
    _report_date_mode = 'as_of'
    _report_filters = ('warehouse', 'product', 'category')
    _report_group_by = ('category', 'product')
    _report_default_group_by = ('category', 'product')
    _report_bar_column = 'quantity'
    _report_compare_keys = ('quantity',)

    @api.model
    def _om_warehouses(self, options):
        domain = [('company_id', 'in', self.env.companies.ids)]
        if options.get('warehouse_ids'):
            domain.append(('id', 'in', options['warehouse_ids']))
        return self.env['stock.warehouse'].search(domain)

    @api.model
    def _om_get_columns(self, options):
        columns = [{'key': 'wh_%s' % warehouse.id, 'label': warehouse.code or warehouse.name, 'type': 'float',
                    'aggregate': 'sum', 'help': warehouse.name}
                   for warehouse in self._om_warehouses(options)]
        columns += [
            {'key': 'quantity', 'label': self.env._("Total"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]
        return columns

    @api.model
    def _om_get_rows(self, options):
        if self._om_is_today(options):
            location_ids = self._om_location_ids(options)
            conditions = [SQL("q.location_id = ANY(%s)", location_ids), SQL("pt.is_storable")]
            product_ids = self._om_product_ids(options)
            if product_ids is not None:
                conditions.append(SQL("q.product_id = ANY(%s)", product_ids))
            self.env.cr.execute(SQL("""
                SELECT q.product_id, loc.warehouse_id, SUM(q.quantity) AS quantity
                  FROM stock_quant q
                  JOIN stock_location loc ON loc.id = q.location_id
                  JOIN product_product pp ON pp.id = q.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                 WHERE %s
              GROUP BY q.product_id, loc.warehouse_id
            """, SQL(" AND ").join(conditions)))
            cells = self.env.cr.dictfetchall()
        else:
            balances = self._om_move_balances({**options, 'group_by': ['product', 'location']},
                                              dims={'product', 'location'})
            warehouse_by_location = {
                loc.id: loc.warehouse_id.id
                for loc in self.env['stock.location'].browse({b['location_id'] for b in balances})
            }
            cells = [{'product_id': b['product_id'], 'warehouse_id': warehouse_by_location.get(b['location_id']),
                      'quantity': b['closing']} for b in balances]
        rows = defaultdict(lambda: defaultdict(float))
        for cell in cells:
            row = rows[cell['product_id']]
            row['wh_%s' % cell['warehouse_id']] += cell['quantity']
            row['quantity'] += cell['quantity']
        return [{'product_id': product_id, **values} for product_id, values in rows.items()]

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['rows']
        warehouses = self._om_warehouses(options)
        kpis = [{'key': 'quantity', 'label': self.env._("Units on hand"),
                 'value': data['total']['values'].get('quantity', 0), 'type': 'float', 'icon': 'inventory_2'}]
        for warehouse in warehouses[:4]:
            key = 'wh_%s' % warehouse.id
            kpis.append({'key': key, 'label': warehouse.name, 'value': data['total']['values'].get(key, 0),
                         'type': 'float', 'icon': 'storefront'})
        single = [r for r in rows if len([w for w in warehouses if r.get('wh_%s' % w.id)]) == 1]
        if len(warehouses) > 1:
            kpis.append({'key': 'single', 'label': self.env._("In one warehouse only"), 'value': len(single),
                         'type': 'int', 'icon': 'location_on', 'filter': 'single'})
        return kpis

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'single':
            warehouses = self._om_warehouses(options)
            return [r for r in rows if len([w for w in warehouses if r.get('wh_%s' % w.id)]) == 1]
        return rows
