from odoo import api, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)


class OmInventoryReportNegative(models.AbstractModel):
    """Quants below zero: stock that left before it was received, to clean up."""
    _name = 'om.inventory.report.negative'
    _inherit = 'om.inventory.report'
    _description = 'Negative Stock Report'

    _report_key = 'negative'
    _report_name = _lt('Negative Stock')
    _report_section = 'stock'
    _report_sequence = 40
    _report_icon = 'warning'
    _report_description = _lt('Products whose quantity is below zero in a location.')
    _report_date_mode = 'none'
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot')
    _report_group_by = ('category', 'product', 'warehouse', 'location', 'lot')
    _report_default_group_by = ('warehouse', 'location')
    _report_expand_default = True
    _report_bar_column = 'quantity'

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'quantity', 'label': self.env._("Quantity"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
            {'key': 'in_date', 'label': self.env._("Since"), 'type': 'datetime'},
        ]

    @api.model
    def _om_row_dimensions(self, options):
        return super()._om_row_dimensions(options) | {'location', 'lot'}

    @api.model
    def _om_get_rows(self, options):
        conditions = [
            SQL("q.location_id = ANY(%s)", self._om_location_ids(options)),
            SQL("q.quantity < 0"),
            SQL("pt.is_storable"),
        ]
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            conditions.append(SQL("q.product_id = ANY(%s)", product_ids))
        if options.get('lot_ids'):
            conditions.append(SQL("q.lot_id = ANY(%s)", options['lot_ids']))
        self.env.cr.execute(SQL("""
            SELECT q.product_id, q.location_id, q.lot_id, SUM(q.quantity) AS quantity, MIN(q.in_date) AS in_date
              FROM stock_quant q
              JOIN product_product pp ON pp.id = q.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE %s
          GROUP BY q.product_id, q.location_id, q.lot_id
        """, SQL(" AND ").join(conditions)))
        return self.env.cr.dictfetchall()

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        dates = [r['in_date'] for r in node['rows'] if r.get('in_date')]
        node['values']['in_date'] = min(dates) if dates else False

    @api.model
    def _om_toggles(self, options):
        return [t for t in super()._om_toggles(options) if t['key'] != 'hide_zero']

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['rows']
        return [
            {'key': 'lines', 'label': self.env._("Negative lines"), 'value': len(rows), 'type': 'int',
             'icon': 'warning', 'tone': 'danger' if rows else 'success'},
            {'key': 'products', 'label': self.env._("Products"), 'value': len({r['product_id'] for r in rows}),
             'type': 'int', 'icon': 'package_2'},
            {'key': 'locations', 'label': self.env._("Locations"), 'value': len({r['location_id'] for r in rows}),
             'type': 'int', 'icon': 'location_on'},
            {'key': 'quantity', 'label': self.env._("Missing units"), 'value': -sum(r['quantity'] for r in rows),
             'type': 'float', 'icon': 'remove_circle'},
        ]
