from odoo import api, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)


class OmInventoryReportStockOnHand(models.AbstractModel):
    """What is in stock: today from the quants (with reservations and
    packages), on a past date from the done moves."""
    _name = 'om.inventory.report.stock_on_hand'
    _inherit = 'om.inventory.report'
    _description = 'Stock on Hand Report'

    _report_key = 'stock_on_hand'
    _report_name = _lt('Stock on Hand')
    _report_section = 'stock'
    _report_sequence = 10
    _report_icon = 'inventory_2'
    _report_description = _lt('Quantities in stock today or on any past date.')
    _report_date_mode = 'as_of'
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot', 'owner')
    _report_group_by = ('category', 'product', 'warehouse', 'location', 'lot', 'package', 'owner')
    _report_default_group_by = ('category', 'product')
    _report_has_details = True
    _report_bar_column = 'quantity'
    _report_compare_keys = ('quantity',)

    @api.model
    def _om_get_columns(self, options):
        today = self._om_is_today(options)
        columns = [
            {'key': 'quantity', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]
        if today:
            columns[1:1] = [
                {'key': 'reserved', 'label': self.env._("Reserved"), 'type': 'float', 'aggregate': 'sum'},
                {'key': 'available', 'label': self.env._("Available"), 'type': 'float', 'aggregate': 'sum'},
            ]
        return columns

    @api.model
    def _om_normalize_options(self, options):
        options = super()._om_normalize_options(options)
        if not self._om_is_today(options) and 'package' in options['group_by']:
            options['group_by'] = [g for g in options['group_by'] if g != 'package'] or ['product']
        return options

    @api.model
    def _om_row_dimensions(self, options):
        dims = super()._om_row_dimensions(options)
        if self._om_is_today(options):
            dims.add('location')
        return dims

    @api.model
    def _om_quant_conditions(self, options):
        location_ids = self._om_location_ids(options)
        conditions = [
            SQL("q.location_id = ANY(%s)", location_ids),
            SQL("pt.is_storable"),
        ]
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            conditions.append(SQL("q.product_id = ANY(%s)", product_ids))
        if options.get('lot_ids'):
            conditions.append(SQL("q.lot_id = ANY(%s)", options['lot_ids']))
        if options.get('owner_ids'):
            conditions.append(SQL("q.owner_id = ANY(%s)", options['owner_ids']))
        return conditions

    @api.model
    def _om_get_rows(self, options):
        if not self._om_is_today(options):
            rows = self._om_move_balances(options)
            for row in rows:
                row['quantity'] = row.pop('closing')
            return rows
        dims = self._om_row_dimensions(options)
        columns = [c for d, c in (('product', 'product_id'), ('location', 'location_id'), ('lot', 'lot_id'),
                                  ('package', 'package_id'), ('owner', 'owner_id')) if d in dims]
        self.env.cr.execute(SQL("""
            SELECT %(group)s, SUM(q.quantity) AS quantity, SUM(q.reserved_quantity) AS reserved,
                   SUM(q.quantity - q.reserved_quantity) AS available
              FROM stock_quant q
              JOIN product_product pp ON pp.id = q.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE %(where)s
          GROUP BY %(group)s
        """, group=SQL(", ").join(SQL.identifier('q', c) for c in columns),
            where=SQL(" AND ").join(self._om_quant_conditions(options))))
        return self.env.cr.dictfetchall()

    @api.model
    def _om_has_details(self, options):
        # the quants of a leaf, when the grouping does not already go down to them
        return self._om_is_today(options) and not {'location', 'lot', 'package'} <= set(options['group_by'])

    @api.model
    def _om_detail_lines(self, node, options):
        node_options, location_ids = self._om_node_scope(options, node)
        domain = [('location_id', 'in', location_ids), ('product_id.is_storable', '=', True)]
        product_ids = self._om_product_ids(node_options)
        if product_ids is not None:
            domain.append(('product_id', 'in', product_ids))
        node_filters = self._om_node_filters(node)
        for option, field in (('lot_ids', 'lot_id'), ('owner_ids', 'owner_id')):
            ids = node_filters.get(option) or options.get(option)
            if ids:
                domain.append((field, 'in', ids))
        if node.get('dim') == 'package' or 'package-' in node['id']:
            package_id = next((int(p.split('-')[1]) for p in node['id'].split('|') if p.startswith('package-')), 0)
            domain.append(('package_id', '=', package_id or False))
        quants = self.env['stock.quant'].search(domain, order='location_id, product_id, lot_id')
        lines = []
        for index, quant in enumerate(quants):
            if options['hide_zero'] and not quant.quantity:
                continue
            parts = [quant.location_id.complete_name]
            if 'product' not in options['group_by']:
                parts.insert(0, quant.product_id.display_name)
            parts += [p for p in (quant.lot_id.name, quant.package_id.name, quant.owner_id.display_name) if p]
            lines.append(self._om_detail_line(node, index, ' · '.join(parts), {
                'quantity': quant.quantity,
                'reserved': quant.reserved_quantity,
                'available': quant.quantity - quant.reserved_quantity,
                'uom': quant.product_id.uom_id.display_name,
            }, open_action={'res_model': 'stock.quant', 'res_id': quant.id}))
        return lines

    @api.model
    def _om_get_kpis(self, data, options):
        total = data['total']['values']
        rows = data['rows']
        products = {r['product_id'] for r in rows if (r.get('quantity') or 0) > 0}
        negative = [r for r in data['all_rows'] if (r.get('quantity') or 0) < 0]
        kpis = [
            {'key': 'products', 'label': self.env._("Products in stock"), 'value': len(products), 'type': 'int',
             'icon': 'package_2'},
            {'key': 'quantity', 'label': self.env._("Units on hand"), 'value': total.get('quantity', 0),
             'type': 'float', 'icon': 'inventory_2'},
        ]
        if self._om_is_today(options):
            kpis.append({'key': 'reserved', 'label': self.env._("Reserved"), 'value': total.get('reserved', 0),
                         'type': 'float', 'icon': 'lock', 'filter': 'reserved'})
        kpis.append({'key': 'negative', 'label': self.env._("Negative lines"), 'value': len(negative),
                     'type': 'int', 'icon': 'warning', 'tone': 'danger' if negative else 'success',
                     'filter': 'negative'})
        return kpis

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'negative':
            return [r for r in rows if (r.get('quantity') or 0) < 0]
        if kpi == 'reserved':
            return [r for r in rows if (r.get('reserved') or 0) > 0]
        return rows

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options['kpi_filter'] == 'negative':
            # negative lines are what is asked for, even when "hide zero" is on
            return self._om_kpi_filter_rows(rows, 'negative', options)
        return super()._om_filter_rows(rows, options, columns)
