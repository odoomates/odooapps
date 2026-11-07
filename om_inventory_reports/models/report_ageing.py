from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate
from odoo.tools import SQL

_lt = LazyTranslate(__name__)

BUCKETS = 5


class OmInventoryReportAgeing(models.AbstractModel):
    """How long the stock has been there: quantities by age bucket, from the
    date each quant came in."""
    _name = 'om.inventory.report.ageing'
    _inherit = 'om.inventory.report'
    _description = 'Stock Ageing Report'

    _report_key = 'ageing'
    _report_name = _lt('Stock Ageing')
    _report_section = 'analysis'
    _report_sequence = 50
    _report_icon = 'hourglass_bottom'
    _report_description = _lt('Stock by age: how long it has been in the warehouse.')
    _report_date_mode = 'none'
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot', 'owner')
    _report_group_by = ('category', 'product', 'warehouse', 'location', 'lot')
    _report_default_group_by = ('category', 'product')
    _report_extra_options = {'period_days': 30}
    _report_bar_column = 'quantity'

    @api.model
    def _om_period(self, options):
        return max(int(options.get('period_days') or 30), 1)

    @api.model
    def _om_bucket_labels(self, options):
        period = self._om_period(options)
        labels = []
        for index in range(BUCKETS - 1):
            labels.append(self.env._("%(start)s-%(end)s days", start=index * period + (index > 0), end=(index + 1) * period))
        labels.append(self.env._("Over %s days", (BUCKETS - 1) * period))
        return labels

    @api.model
    def _om_get_columns(self, options):
        columns = [{'key': 'quantity', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum',
                    'optional': False}]
        for index, label in enumerate(self._om_bucket_labels(options)):
            columns.append({'key': 'b%s' % index, 'label': label, 'type': 'float', 'aggregate': 'sum'})
        columns += [
            {'key': 'age_avg', 'label': self.env._("Average Age"), 'type': 'days',
             'help': self.env._("Average age of the units, weighted by quantity.")},
            {'key': 'in_date', 'label': self.env._("Oldest Since"), 'type': 'datetime', 'visible': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]
        return columns

    @api.model
    def _om_row_dimensions(self, options):
        return super()._om_row_dimensions(options) | {'location', 'lot'}

    @api.model
    def _om_get_rows(self, options):
        period = self._om_period(options)
        now = fields.Datetime.now()
        conditions = [
            SQL("q.location_id = ANY(%s)", self._om_location_ids(options)),
            SQL("q.quantity > 0"),
            SQL("pt.is_storable"),
        ]
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            conditions.append(SQL("q.product_id = ANY(%s)", product_ids))
        for option, column in (('lot_ids', 'lot_id'), ('owner_ids', 'owner_id')):
            if options.get(option):
                conditions.append(SQL("%s = ANY(%s)", SQL.identifier('q', column), options[option]))
        buckets = []
        for index in range(BUCKETS):
            low = index * period
            if index == BUCKETS - 1:
                condition = SQL("a.age > %s", low)
            elif index == 0:
                condition = SQL("a.age <= %s", period)
            else:
                condition = SQL("a.age > %s AND a.age <= %s", low, low + period)
            buckets.append(SQL("COALESCE(SUM(a.quantity) FILTER (WHERE %s), 0) AS %s",
                               condition, SQL.identifier('b%s' % index)))
        self.env.cr.execute(SQL("""
            SELECT a.product_id, a.location_id, a.lot_id, SUM(a.quantity) AS quantity, %(buckets)s,
                   SUM(a.quantity * a.age) AS age_weight, MIN(a.in_date) AS in_date
              FROM (
                SELECT q.product_id, q.location_id, q.lot_id, q.quantity, q.in_date,
                       GREATEST(EXTRACT(EPOCH FROM (%(now)s - q.in_date)) / 86400.0, 0) AS age
                  FROM stock_quant q
                  JOIN product_product pp ON pp.id = q.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
                 WHERE %(where)s
              ) a
          GROUP BY a.product_id, a.location_id, a.lot_id
        """, buckets=SQL(", ").join(buckets), now=now, where=SQL(" AND ").join(conditions)))
        return self.env.cr.dictfetchall()

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        quantity = sum(r['quantity'] for r in node['rows'])
        weight = sum(r['age_weight'] for r in node['rows'])
        node['values']['age_avg'] = weight / quantity if quantity else 0.0
        dates = [r['in_date'] for r in node['rows'] if r.get('in_date')]
        node['values']['in_date'] = min(dates) if dates else False
        oldest = 'b%s' % (BUCKETS - 1)
        if node['values'].get(oldest, 0.0) > 0:
            node['values'][oldest + '_tone'] = 'danger'

    @api.model
    def _om_extra_options_meta(self, options):
        return [{'key': 'period_days', 'label': self.env._("Days per bucket"), 'min': 1, 'step': 1}]

    @api.model
    def _om_get_kpis(self, data, options):
        total = data['total']['values']
        quantity = total.get('quantity') or 0.0
        old_index = BUCKETS - 2
        old = sum(total.get('b%s' % i, 0.0) for i in range(old_index, BUCKETS))
        labels = self._om_bucket_labels(options)
        return [
            {'key': 'quantity', 'label': self.env._("Units on hand"), 'value': quantity, 'type': 'float',
             'icon': 'inventory_2'},
            {'key': 'age', 'label': self.env._("Average age"), 'value': total.get('age_avg', 0), 'type': 'days',
             'icon': 'hourglass_bottom'},
            {'key': 'old', 'label': self.env._("Older than %s days", self._om_period(options) * old_index),
             'value': old, 'type': 'float', 'icon': 'history', 'tone': 'warning' if old else 'success',
             'filter': 'old'},
            {'key': 'old_share', 'label': self.env._("Share of old stock"),
             'value': old / quantity * 100 if quantity else 0.0, 'type': 'percent', 'icon': 'pie_chart',
             'tone': 'warning' if old else 'success'},
            {'key': 'oldest', 'label': labels[-1], 'value': total.get('b%s' % (BUCKETS - 1), 0), 'type': 'float',
             'icon': 'warning', 'tone': 'danger' if total.get('b%s' % (BUCKETS - 1)) else 'success',
             'filter': 'oldest'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'old':
            return [r for r in rows if any(r.get('b%s' % i) for i in range(BUCKETS - 2, BUCKETS))]
        if kpi == 'oldest':
            return [r for r in rows if r.get('b%s' % (BUCKETS - 1))]
        return rows
