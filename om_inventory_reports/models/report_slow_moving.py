from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)

# what counts as the stock being used: sold or consumed
USE_KINDS = ('out_sale', 'out_production')


class OmInventoryReportSlowMoving(models.AbstractModel):
    """Stock that does not move: products in stock with their last issue,
    the days since, and what was issued in the period."""
    _name = 'om.inventory.report.slow_moving'
    _inherit = 'om.inventory.report'
    _description = 'Slow-Moving and Dead Stock Report'

    _report_key = 'slow_moving'
    _report_name = _lt('Slow-Moving & Dead Stock')
    _report_section = 'analysis'
    _report_sequence = 55
    _report_icon = 'speed'
    _report_description = _lt('Products in stock that are not sold or used: days since the last issue.')
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('status', 'category', 'product', 'warehouse', 'location')
    _report_default_group_by = ('status', 'product')
    _report_extra_options = {'idle_days': 90}
    _report_bar_column = 'closing'

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['status'] = {
            'label': self.env._("Status"),
            'icon': 'speed',
            'selection': {
                'dead': self.env._("Dead stock: never issued"),
                'slow': self.env._("Slow moving"),
                'active': self.env._("Moving"),
            },
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'closing', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'issued', 'label': self.env._("Issued in Period"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("Delivered to customers and consumed in production during the period.")},
            {'key': 'received', 'label': self.env._("Received in Period"), 'type': 'float', 'aggregate': 'sum',
             'visible': False},
            {'key': 'last_out', 'label': self.env._("Last Issue"), 'type': 'datetime'},
            {'key': 'last_in', 'label': self.env._("Last Receipt"), 'type': 'datetime', 'visible': False},
            {'key': 'idle_days', 'label': self.env._("Days Without Issue"), 'type': 'days'},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_row_dimensions(self, options):
        dims = set(options['group_by']) - {'status'} | {'product'}
        if 'warehouse' in dims:
            dims.add('location')
        return dims

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        rows = self._om_move_balances(options, start, end)
        rows = [r for r in rows if r['closing'] > 0]
        if not rows:
            return []
        dims = self._om_row_dimensions(options)
        keys = ['product_id'] + (['location_id'] if 'location' in dims else [])
        dates = self._om_last_dates(options, end, keys)
        idle_days = int(options.get('idle_days') or 90)
        today = fields.Date.to_date(options['date_to'])
        for row in rows:
            row['issued'] = sum(row[k] for k in USE_KINDS)
            row['received'] = row['in_purchase'] + row['in_production']
            last = dates.get(tuple(row[k] for k in keys), {})
            row['last_out'] = last.get('last_out') or False
            row['last_in'] = last.get('last_in') or False
            since = row['last_out'] or last.get('first_in')
            row['idle_days'] = (today - fields.Datetime.to_datetime(since).date()).days if since else 0
            if not row['last_out']:
                row['status_id'] = 'dead'
            elif row['idle_days'] >= idle_days:
                row['status_id'] = 'slow'
            else:
                row['status_id'] = 'active'
        return rows

    @api.model
    def _om_last_dates(self, options, end, keys):
        location_ids = self._om_location_ids(options)
        sides = self._om_move_sides(options, location_ids, end)
        group = SQL(", ").join(SQL.identifier('s', k) for k in keys)
        self.env.cr.execute(SQL("""
            SELECT %(group)s,
                   MAX(s.date) FILTER (WHERE s.kind = ANY(%(use)s)) AS last_out,
                   MAX(s.date) FILTER (WHERE s.qty > 0 AND s.kind != 'in_internal') AS last_in,
                   MIN(s.date) FILTER (WHERE s.qty > 0) AS first_in
              FROM (%(sides)s) s
          GROUP BY %(group)s
        """, group=group, use=list(USE_KINDS), sides=sides))
        return {tuple(row[k] for k in keys): row for row in self.env.cr.dictfetchall()}

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        rows = node['rows']
        outs = [r['last_out'] for r in rows if r.get('last_out')]
        ins = [r['last_in'] for r in rows if r.get('last_in')]
        node['values']['last_out'] = max(outs) if outs else False
        node['values']['last_in'] = max(ins) if ins else False
        idle = [r['idle_days'] for r in rows]
        node['values']['idle_days'] = min(idle) if idle else 0
        idle_days = int(options.get('idle_days') or 90)
        if node['values']['idle_days'] >= idle_days:
            node['values']['idle_days_tone'] = 'danger' if not outs else 'warning'

    @api.model
    def _om_extra_options_meta(self, options):
        return [{'key': 'idle_days', 'label': self.env._("Slow after (days)"), 'min': 1, 'step': 1}]

    @api.model
    def _om_toggles(self, options):
        return [t for t in super()._om_toggles(options) if t['key'] != 'hide_zero']

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        dead = [r for r in rows if r['status_id'] == 'dead']
        slow = [r for r in rows if r['status_id'] == 'slow']
        products = {r['product_id'] for r in rows}
        return [
            {'key': 'products', 'label': self.env._("Products in stock"), 'value': len(products), 'type': 'int',
             'icon': 'package_2'},
            {'key': 'dead', 'label': self.env._("Dead stock products"), 'value': len({r['product_id'] for r in dead}),
             'type': 'int', 'icon': 'block', 'tone': 'danger' if dead else 'success', 'filter': 'dead'},
            {'key': 'slow', 'label': self.env._("Slow-moving products"), 'value': len({r['product_id'] for r in slow}),
             'type': 'int', 'icon': 'hourglass_bottom', 'tone': 'warning' if slow else 'success', 'filter': 'slow'},
            {'key': 'dead_qty', 'label': self.env._("Units in dead stock"), 'value': sum(r['closing'] for r in dead),
             'type': 'float', 'icon': 'inventory_2', 'tone': 'danger' if dead else 'neutral'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi in ('dead', 'slow'):
            return [r for r in rows if r['status_id'] == kpi]
        return rows
