from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)


class OmInventoryReportTransfers(models.AbstractModel):
    """The transfers of a period by operation type and status: how many, how
    many are late, and how late the done ones were."""
    _name = 'om.inventory.report.transfers'
    _inherit = 'om.inventory.report'
    _description = 'Transfers Report'

    _report_key = 'transfers'
    _report_name = _lt('Transfers')
    _report_section = 'operations'
    _report_sequence = 80
    _report_icon = 'local_shipping'
    _report_description = _lt('Receipts, deliveries and internal transfers: late, on time, delays.')
    _report_filters = ('warehouse', 'picking_type', 'partner', 'product')
    _report_group_by = ('picking_type', 'state', 'partner', 'warehouse')
    _report_default_group_by = ('picking_type', 'state')
    _report_has_details = True
    _report_bar_column = 'count'
    _report_compare_keys = ('count', 'late')
    _report_extra_options = {'include_cancelled': False}

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        states = dict(self.env['stock.picking']._fields['state']._description_selection(self.env))
        dimensions['state'] = {'label': self.env._("Status"), 'icon': 'flag', 'selection': states}
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'scheduled_date', 'label': self.env._("Scheduled"), 'type': 'datetime', 'detail_only': True},
            {'key': 'date_done', 'label': self.env._("Done"), 'type': 'datetime', 'detail_only': True},
            {'key': 'partner', 'label': self.env._("Partner"), 'type': 'char', 'detail_only': True},
            {'key': 'origin', 'label': self.env._("Source"), 'type': 'char', 'detail_only': True},
            {'key': 'count', 'label': self.env._("Transfers"), 'type': 'int', 'aggregate': 'sum', 'optional': False},
            {'key': 'late', 'label': self.env._("Late"), 'type': 'int', 'aggregate': 'sum',
             'help': self.env._("Not done and past the scheduled date.")},
            {'key': 'done_late', 'label': self.env._("Done Late"), 'type': 'int', 'aggregate': 'sum',
             'help': self.env._("Done after the scheduled date.")},
            {'key': 'quantity', 'label': self.env._("Quantity"), 'type': 'float', 'aggregate': 'sum',
             'visible': False},
            {'key': 'delay', 'label': self.env._("Average Delay"), 'type': 'days',
             'help': self.env._("Days between the scheduled date and the done date, for done transfers.")},
        ]

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        now = fields.Datetime.now()
        conditions = [
            SQL("sp.company_id = ANY(%s)", self.env.companies.ids),
            SQL("COALESCE(sp.date_done, sp.scheduled_date) >= %s", start),
            SQL("COALESCE(sp.date_done, sp.scheduled_date) < %s", end),
        ]
        if not options.get('include_cancelled'):
            conditions.append(SQL("sp.state != 'cancel'"))
        if options.get('warehouse_ids'):
            conditions.append(SQL("spt.warehouse_id = ANY(%s)", options['warehouse_ids']))
        if options.get('picking_type_ids'):
            conditions.append(SQL("sp.picking_type_id = ANY(%s)", options['picking_type_ids']))
        if options.get('partner_ids'):
            partners = self.env['res.partner'].with_context(active_test=False).search(
                [('id', 'child_of', options['partner_ids'])]).ids
            conditions.append(SQL("sp.partner_id = ANY(%s)", partners))
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            conditions.append(SQL(
                "EXISTS (SELECT 1 FROM stock_move m WHERE m.picking_id = sp.id AND m.product_id = ANY(%s))",
                product_ids))
        self.env.cr.execute(SQL("""
            SELECT sp.id AS picking_id, sp.name, sp.origin, sp.picking_type_id, sp.partner_id, sp.state AS state_id,
                   spt.warehouse_id, sp.scheduled_date, sp.date_done,
                   1 AS count,
                   CASE WHEN sp.state NOT IN ('done', 'cancel') AND sp.scheduled_date < %(now)s THEN 1 ELSE 0 END AS late,
                   CASE WHEN sp.state = 'done' AND sp.date_done > sp.scheduled_date + INTERVAL '1 day' THEN 1 ELSE 0 END AS done_late,
                   CASE WHEN sp.state = 'done'
                        THEN EXTRACT(EPOCH FROM (sp.date_done - sp.scheduled_date)) / 86400.0 END AS delay,
                   (SELECT COALESCE(SUM(m.product_qty), 0) FROM stock_move m WHERE m.picking_id = sp.id) AS quantity
              FROM stock_picking sp
              JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
             WHERE %(where)s
        """, now=now, where=SQL(" AND ").join(conditions)))
        return self.env.cr.dictfetchall()

    @api.model
    def _om_enrich_rows(self, rows, options):
        return rows

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options['kpi_filter']:
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        delays = [r['delay'] for r in node['rows'] if r['delay'] is not None]
        node['values']['delay'] = sum(delays) / len(delays) if delays else False
        if node['values'].get('late'):
            node['values']['late_tone'] = 'danger'
        if node['values'].get('done_late'):
            node['values']['done_late_tone'] = 'warning'

    @api.model
    def _om_detail_lines(self, node, options):
        partners = self._om_names('partner', list({r['partner_id'] for r in node['rows'] if r['partner_id']}))
        rows = sorted(node['rows'], key=lambda r: r['date_done'] or r['scheduled_date'], reverse=True)
        return [self._om_detail_line(node, row['picking_id'], row['name'], {
            'scheduled_date': row['scheduled_date'],
            'date_done': row['date_done'],
            'partner': partners.get(row['partner_id'], ''),
            'origin': row['origin'] or '',
            'count': 1,
            'late': row['late'],
            'done_late': row['done_late'],
            'quantity': row['quantity'],
            'delay': row['delay'] if row['delay'] is not None else False,
            'late_tone': 'danger' if row['late'] else False,
        }, open_action={'res_model': 'stock.picking', 'res_id': row['picking_id']}) for row in rows]

    @api.model
    def _om_node_links(self, node, options):
        return []

    @api.model
    def _om_toggles(self, options):
        return [{'key': 'include_cancelled', 'label': self.env._("Include cancelled transfers")}]

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        done = [r for r in rows if r['state_id'] == 'done']
        late = [r for r in rows if r['late']]
        done_late = [r for r in done if r['done_late']]
        on_time = (len(done) - len(done_late)) / len(done) * 100 if done else 0.0
        return [
            {'key': 'count', 'label': self.env._("Transfers"), 'value': len(rows), 'type': 'int',
             'icon': 'local_shipping'},
            {'key': 'done', 'label': self.env._("Done"), 'value': len(done), 'type': 'int', 'icon': 'check_circle',
             'tone': 'success', 'filter': 'done'},
            {'key': 'open', 'label': self.env._("To do"), 'value': len(rows) - len(done), 'type': 'int',
             'icon': 'schedule', 'filter': 'open'},
            {'key': 'late', 'label': self.env._("Late"), 'value': len(late), 'type': 'int', 'icon': 'warning',
             'tone': 'danger' if late else 'success', 'filter': 'late'},
            {'key': 'on_time', 'label': self.env._("Done on time"), 'value': on_time, 'type': 'percent',
             'icon': 'timer', 'tone': 'success' if on_time >= 90 else 'warning'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'done':
            return [r for r in rows if r['state_id'] == 'done']
        if kpi == 'open':
            return [r for r in rows if r['state_id'] not in ('done', 'cancel')]
        if kpi == 'late':
            return [r for r in rows if r['late']]
        return rows
