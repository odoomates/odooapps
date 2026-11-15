from odoo import api, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)


class OmInventoryReportAdjustments(models.AbstractModel):
    """Every inventory adjustment and scrap of the period: what was found,
    lost or thrown away, where, and by which operation."""
    _name = 'om.inventory.report.adjustments'
    _inherit = 'om.inventory.report'
    _description = 'Adjustments and Scrap Report'

    _report_key = 'adjustments'
    _report_name = _lt('Adjustments & Scrap')
    _report_section = 'operations'
    _report_sequence = 85
    _report_icon = 'published_with_changes'
    _report_description = _lt('Inventory adjustments (gains and losses) and scrapped stock.')
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot')
    _report_group_by = ('kind', 'category', 'product', 'warehouse', 'location', 'lot')
    _report_default_group_by = ('kind', 'product')
    _report_has_details = True
    _report_bar_column = 'net'
    _report_compare_keys = ('net',)

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['kind'] = {
            'label': self.env._("Type"),
            'icon': 'published_with_changes',
            'selection': {
                'gain': self.env._("Adjustment: found"),
                'loss': self.env._("Adjustment: lost"),
                'scrap': self.env._("Scrapped"),
            },
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': self.env._("Date"), 'type': 'datetime', 'detail_only': True},
            {'key': 'location', 'label': self.env._("Location"), 'type': 'char', 'detail_only': True},
            {'key': 'lot', 'label': self.env._("Lot/Serial"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'gain', 'label': self.env._("Found"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'loss', 'label': self.env._("Lost"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'scrap', 'label': self.env._("Scrapped"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'net', 'label': self.env._("Net"), 'type': 'float', 'aggregate': 'sum', 'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        location_ids = self._om_location_ids(options)
        if not location_ids:
            return []
        sides = self._om_move_sides(options, location_ids, end,
                                    extra=SQL("(sm.is_inventory OR sm.is_scrap)"))
        self.env.cr.execute(SQL("""
            SELECT s.id AS line_id, s.move_id, s.picking_id, s.product_id, s.location_id, s.lot_id, s.date, s.qty,
                   s.kind, sm.reference, sm.is_scrap
              FROM (%s) s
              JOIN stock_move sm ON sm.id = s.move_id
             WHERE s.date >= %s AND s.kind NOT IN ('in_internal', 'out_internal')
        """, sides, start))
        rows = self.env.cr.dictfetchall()
        for row in rows:
            if row['is_scrap']:
                row['kind_id'] = 'scrap'
            else:
                row['kind_id'] = 'gain' if row['qty'] > 0 else 'loss'
            row['gain'] = row['qty'] if row['kind_id'] == 'gain' else 0.0
            row['loss'] = -row['qty'] if row['kind_id'] == 'loss' else 0.0
            row['scrap'] = -row['qty'] if row['kind_id'] == 'scrap' else 0.0
            row['net'] = row['qty']
        return rows

    @api.model
    def _om_detail_lines(self, node, options):
        rows = sorted(node['rows'], key=lambda r: r['date'], reverse=True)
        locations = self._om_names('location', list({r['location_id'] for r in rows}))
        lots = self._om_names('lot', list({r['lot_id'] for r in rows if r['lot_id']}))
        products = self._om_names('product', list({r['product_id'] for r in rows}))
        show_product = 'product' not in options['group_by']
        lines = []
        for row in rows:
            name = row['reference'] or ''
            if show_product:
                name = '%s · %s' % (products.get(row['product_id'], ''), name)
            lines.append(self._om_detail_line(node, row['line_id'] * (1 if row['qty'] > 0 else -1), name, {
                'date': row['date'],
                'location': locations.get(row['location_id'], ''),
                'lot': lots.get(row['lot_id'], ''),
                'gain': row['gain'], 'loss': row['loss'], 'scrap': row['scrap'], 'net': row['net'],
                'uom': row.get('uom'),
            }, open_action=self._om_move_open(row)))
        return lines

    @api.model
    def _om_get_kpis(self, data, options):
        total = data['total']['values']
        return [
            {'key': 'gain', 'label': self.env._("Found"), 'value': total.get('gain', 0), 'type': 'float',
             'icon': 'add_circle', 'tone': 'success', 'filter': 'gain'},
            {'key': 'loss', 'label': self.env._("Lost"), 'value': total.get('loss', 0), 'type': 'float',
             'icon': 'remove_circle', 'tone': 'danger', 'filter': 'loss'},
            {'key': 'scrap', 'label': self.env._("Scrapped"), 'value': total.get('scrap', 0), 'type': 'float',
             'icon': 'delete', 'tone': 'warning', 'filter': 'scrap'},
            {'key': 'net', 'label': self.env._("Net change"), 'value': total.get('net', 0), 'type': 'float',
             'icon': 'sync_alt'},
            {'key': 'lines', 'label': self.env._("Operations"), 'value': len(data['rows']), 'type': 'int',
             'icon': 'checklist'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi in ('gain', 'loss', 'scrap'):
            return [r for r in rows if r['kind_id'] == kpi]
        return rows
