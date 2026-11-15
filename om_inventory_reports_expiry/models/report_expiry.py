from datetime import timedelta

from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)


class OmInventoryReportExpiry(models.AbstractModel):
    """Stock of lots with an expiration date, by how soon they expire."""
    _name = 'om.inventory.report.expiry'
    _inherit = 'om.inventory.report'
    _description = 'Lot Expiry Report'

    _report_key = 'expiry'
    _report_name = _lt('Lot Expiry')
    _report_section = 'stock'
    _report_sequence = 52
    _report_icon = 'event_busy'
    _report_description = _lt('Lots in stock by expiration date: expired, expiring soon, later.')
    _report_date_mode = 'none'
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot')
    _report_group_by = ('window', 'category', 'product', 'warehouse', 'location', 'lot')
    _report_default_group_by = ('window', 'product', 'lot')
    _report_extra_options = {'soon_days': 30}
    _report_bar_column = 'quantity'

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['window'] = {
            'label': self.env._("Expiry"),
            'icon': 'event_busy',
            'selection': {
                'expired': self.env._("Expired"),
                'alert': self.env._("Alert date reached"),
                'soon': self.env._("Expiring soon"),
                'later': self.env._("Later"),
            },
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'quantity', 'label': self.env._("Quantity"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
            {'key': 'expiration_date', 'label': self.env._("Expiration Date"), 'type': 'datetime'},
            {'key': 'days_left', 'label': self.env._("Days Left"), 'type': 'days'},
            {'key': 'use_date', 'label': self.env._("Best Before"), 'type': 'datetime', 'visible': False},
            {'key': 'removal_date', 'label': self.env._("Removal Date"), 'type': 'datetime', 'visible': False},
        ]

    @api.model
    def _om_row_dimensions(self, options):
        return {'product', 'location', 'lot'}

    @api.model
    def _om_get_rows(self, options):
        conditions = [
            SQL("q.location_id = ANY(%s)", self._om_location_ids(options)),
            SQL("q.quantity > 0"),
            SQL("lot.expiration_date IS NOT NULL"),
        ]
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            conditions.append(SQL("q.product_id = ANY(%s)", product_ids))
        if options.get('lot_ids'):
            conditions.append(SQL("q.lot_id = ANY(%s)", options['lot_ids']))
        self.env.cr.execute(SQL("""
            SELECT q.product_id, q.location_id, q.lot_id, SUM(q.quantity) AS quantity,
                   lot.expiration_date, lot.use_date, lot.removal_date, lot.alert_date
              FROM stock_quant q
              JOIN stock_lot lot ON lot.id = q.lot_id
             WHERE %s
          GROUP BY q.product_id, q.location_id, q.lot_id, lot.expiration_date, lot.use_date, lot.removal_date,
                   lot.alert_date
        """, SQL(" AND ").join(conditions)))
        rows = self.env.cr.dictfetchall()
        now = fields.Datetime.now()
        soon = now + timedelta(days=int(options.get('soon_days') or 30))
        for row in rows:
            row['days_left'] = (row['expiration_date'] - now).total_seconds() / 86400
            if row['expiration_date'] <= now:
                row['window_id'] = 'expired'
            elif row['alert_date'] and row['alert_date'] <= now:
                row['window_id'] = 'alert'
            elif row['expiration_date'] <= soon:
                row['window_id'] = 'soon'
            else:
                row['window_id'] = 'later'
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        rows = node['rows']
        for key in ('expiration_date', 'use_date', 'removal_date'):
            dates = [r[key] for r in rows if r.get(key)]
            node['values'][key] = min(dates) if dates else False
        node['values']['days_left'] = min((r['days_left'] for r in rows), default=False)
        if node['values']['days_left'] is not False:
            if node['values']['days_left'] <= 0:
                node['values']['days_left_tone'] = 'danger'
            elif node['values']['days_left'] <= int(options.get('soon_days') or 30):
                node['values']['days_left_tone'] = 'warning'

    @api.model
    def _om_extra_options_meta(self, options):
        return [{'key': 'soon_days', 'label': self.env._("Expiring soon within (days)"), 'min': 1, 'step': 1}]

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        expired = [r for r in rows if r['window_id'] == 'expired']
        soon = [r for r in rows if r['window_id'] in ('alert', 'soon')]
        return [
            {'key': 'lots', 'label': self.env._("Lots in stock"), 'value': len({r['lot_id'] for r in rows}),
             'type': 'int', 'icon': 'barcode'},
            {'key': 'expired', 'label': self.env._("Expired lots"), 'value': len({r['lot_id'] for r in expired}),
             'type': 'int', 'icon': 'event_busy', 'tone': 'danger' if expired else 'success', 'filter': 'expired'},
            {'key': 'expired_qty', 'label': self.env._("Expired units"), 'value': sum(r['quantity'] for r in expired),
             'type': 'float', 'icon': 'delete', 'tone': 'danger' if expired else 'success', 'filter': 'expired'},
            {'key': 'soon', 'label': self.env._("Expiring within %s days", int(options.get('soon_days') or 30)),
             'value': len({r['lot_id'] for r in soon}), 'type': 'int', 'icon': 'schedule',
             'tone': 'warning' if soon else 'success', 'filter': 'soon'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'expired':
            return [r for r in rows if r['window_id'] == 'expired']
        if kpi == 'soon':
            return [r for r in rows if r['window_id'] in ('alert', 'soon')]
        return rows
