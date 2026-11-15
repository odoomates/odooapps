"""Stock values in the quantity reports."""
from odoo import api, models
from odoo.tools import SQL

from odoo.addons.om_inventory_reports.models.report_ageing import BUCKETS


def value_column(env, key='value', label=None, visible=True, optional=True):
    return {'key': key, 'label': label or env._("Value"), 'type': 'monetary', 'aggregate': 'sum',
            'visible': visible, 'optional': optional}


class OmInventoryReportStockOnHand(models.AbstractModel):
    _inherit = 'om.inventory.report.stock_on_hand'
    _report_compare_keys = ('quantity', 'value')

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        if self._report_key == 'stock_on_hand':
            columns.append(value_column(self.env))
        return columns

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        if self._report_key == 'stock_on_hand':
            start, end = self._om_period_bounds(options)
            self._om_set_values(rows, end, [('quantity', 'value')], options)
        return rows

    @api.model
    def _om_detail_lines(self, node, options):
        lines = super()._om_detail_lines(node, options)
        quantity = node['values'].get('quantity')
        if quantity and self._report_key == 'stock_on_hand':
            unit = node['values'].get('value', 0.0) / quantity
            for line in lines:
                line['values']['value'] = (line['values'].get('quantity') or 0.0) * unit
        return lines

    @api.model
    def _om_get_kpis(self, data, options):
        kpis = super()._om_get_kpis(data, options)
        if self._report_key == 'stock_on_hand':
            kpis.insert(2, {'key': 'value', 'label': self.env._("Stock value"),
                            'value': data['total']['values'].get('value', 0.0), 'type': 'monetary',
                            'icon': 'payments'})
        return kpis


class OmInventoryReportSummary(models.AbstractModel):
    _inherit = 'om.inventory.report.summary'
    _report_compare_keys = ('qty_in', 'qty_out', 'closing', 'closing_value')

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        columns.insert(1, value_column(self.env, 'opening_value', self.env._("Opening Value"), visible=False))
        columns.append(value_column(self.env, 'closing_value', self.env._("Closing Value")))
        return columns

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        start, end = self._om_period_bounds(options)
        self._om_set_values(rows, start, [('opening', 'opening_value')], options)
        for row in rows:
            row.pop('unit_cost', None)
        self._om_set_values(rows, end, [('closing', 'closing_value')], options)
        return rows


class OmInventoryReportStockCard(models.AbstractModel):
    """The value next to the quantity: opening value, the value of each
    receipt and issue, a running value, and the closing value.

    A move is valued at its share of the move's own value (what Odoo booked
    for it). A move with no value of its own (between two warehouses of the
    company) takes the unit cost of the end of the period. What is left
    between the running value and the closing valuation (cost changes,
    revaluations, landed costs) is shown on its own line."""
    _inherit = 'om.inventory.report.stock_card'

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        index = next(i for i, c in enumerate(columns) if c['key'] == 'uom') + 1
        columns[index:index] = [
            value_column(self.env, 'opening_value', self.env._("Opening Value"), visible=False),
            value_column(self.env, 'value_in', self.env._("Value In")),
            value_column(self.env, 'value_out', self.env._("Value Out")),
            {**value_column(self.env, 'revaluation', self.env._("Revaluation"), visible=False),
             'help': self.env._("Cost changes, revaluations and landed costs of the period.")},
            value_column(self.env, 'value_balance', self.env._("Value"), optional=False),
        ]
        return columns

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        if not rows:
            return rows
        start, end = self._om_period_bounds(options)
        self._om_set_values(rows, start, [('opening', 'opening_value')], options)
        for row in rows:
            row.pop('unit_cost', None)
        self._om_set_values(rows, end, [('balance', 'value_balance')], options)
        dims = [k for k in ('product_id', 'location_id', 'lot_id', 'owner_id') if k in rows[0]]
        moved = self._om_moved_values(options, start, end, dims)
        for row in rows:
            values = moved.get(tuple(row[k] for k in dims), {})
            cost = row.get('unit_cost', 0.0)
            row['value_in'] = (values.get('value_in') or 0.0) + (values.get('unvalued_in') or 0.0) * cost
            row['value_out'] = (values.get('value_out') or 0.0) + (values.get('unvalued_out') or 0.0) * cost
            row['revaluation'] = row['value_balance'] - row['opening_value'] - row['value_in'] + row['value_out']
        return rows

    @api.model
    def _om_moved_values(self, options, start, end, dims):
        """{dims: {value_in, value_out, unvalued_in, unvalued_out}} of the period."""
        location_ids = self._om_location_ids(options)
        if not location_ids:
            return {}
        sides = self._om_move_sides(options, location_ids, end)
        group = SQL(", ").join(SQL.identifier('s', k) for k in dims)
        self.env.cr.execute(SQL("""
            SELECT %(group)s,
                   SUM(x.value) FILTER (WHERE s.qty > 0) AS value_in,
                   SUM(-x.value) FILTER (WHERE s.qty < 0) AS value_out,
                   SUM(s.qty) FILTER (WHERE s.qty > 0 AND x.value IS NULL) AS unvalued_in,
                   SUM(-s.qty) FILTER (WHERE s.qty < 0 AND x.value IS NULL) AS unvalued_out
              FROM (%(sides)s) s
              JOIN stock_move sm ON sm.id = s.move_id
              LEFT JOIN LATERAL (
                   SELECT SUM(l.quantity_product_uom) AS qty
                     FROM stock_move_line l
                    WHERE l.move_id = s.move_id AND l.state = 'done') mq ON TRUE
             CROSS JOIN LATERAL (
                   -- the line's share of the move's value, signed like the quantity
                   SELECT CASE WHEN sm.value IS NOT NULL AND sm.value != 0 AND mq.qty != 0
                               THEN ABS(sm.value) * s.qty / mq.qty END AS value) x
             WHERE s.date >= %(start)s
          GROUP BY %(group)s
        """, group=group, sides=sides, start=start))
        return {tuple(r[k] for k in dims): r for r in self.env.cr.dictfetchall()}

    @api.model
    def _om_detail_lines(self, node, options):
        lines = super()._om_detail_lines(node, options)
        move_ids = list({line['values']['move_id'] for line in lines if line['values'].get('move_id')})
        values = {}
        if move_ids:
            self.env.cr.execute(SQL("""
                SELECT sm.id, sm.value, COALESCE(SUM(sml.quantity_product_uom), 0) AS qty
                  FROM stock_move sm
             LEFT JOIN stock_move_line sml ON sml.move_id = sm.id AND sml.state = 'done'
                 WHERE sm.id = ANY(%s)
              GROUP BY sm.id, sm.value
            """, move_ids))
            values = {r['id']: r for r in self.env.cr.dictfetchall()}
        rows = node['rows']
        cost = rows[0].get('unit_cost', 0.0) if len(rows) == 1 else (
            node['values'].get('value_balance', 0.0) / node['values']['balance'] if node['values'].get('balance') else 0.0)
        running = node['values'].get('opening_value', 0.0)
        result = []
        for line in lines:
            line_values = line['values']
            if line['kind'] == 'opening':
                line_values['value_balance'] = running
            elif line['kind'] == 'closing':
                reval = node['values'].get('revaluation', 0.0)
                if abs(reval) >= 0.005:
                    result.append(self._om_detail_line(node, 'reval', self.env._("Revaluations and cost changes"), {
                        'revaluation': reval,
                        'value_in': reval if reval > 0 else 0.0,
                        'value_out': -reval if reval < 0 else 0.0,
                        'value_balance': running + reval,
                        'uom': line_values.get('uom'),
                    }, kind='opening'))
                line_values.update({
                    'value_in': node['values'].get('value_in'),
                    'value_out': node['values'].get('value_out'),
                    'revaluation': node['values'].get('revaluation'),
                    'value_balance': node['values'].get('value_balance'),
                })
            elif line_values.get('move_id'):
                move = values.get(line_values['move_id'], {})
                qty = line_values.get('qty') or 0.0
                if move.get('value') and move.get('qty'):
                    value = abs(move['value']) * qty / move['qty']
                else:
                    value = qty * cost
                running += value
                line_values['value_in'] = value if value > 0 else 0.0
                line_values['value_out'] = -value if value < 0 else 0.0
                line_values['value_balance'] = running
            result.append(line)
        return result


class OmInventoryReportAgeing(models.AbstractModel):
    _inherit = 'om.inventory.report.ageing'

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        columns.insert(1, value_column(self.env))
        columns.append(value_column(self.env, 'old_value', self.env._("Value Over %s Days",
                                                                      self._om_period(options) * (BUCKETS - 2)),
                                    visible=False))
        return columns

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        self._om_set_values(rows, None, [('quantity', 'value')], options)
        for row in rows:
            old = sum(row.get('b%s' % i, 0.0) for i in range(BUCKETS - 2, BUCKETS))
            row['old_value'] = old * row.get('unit_cost', 0.0)
        return rows

    @api.model
    def _om_get_kpis(self, data, options):
        kpis = super()._om_get_kpis(data, options)
        total = data['total']['values']
        kpis.insert(1, {'key': 'value', 'label': self.env._("Stock value"), 'value': total.get('value', 0.0),
                        'type': 'monetary', 'icon': 'payments'})
        kpis.append({'key': 'old_value', 'label': self.env._("Value of old stock"),
                     'value': total.get('old_value', 0.0), 'type': 'monetary', 'icon': 'history',
                     'tone': 'warning' if total.get('old_value') else 'success', 'filter': 'old'})
        return kpis


class OmInventoryReportSlowMoving(models.AbstractModel):
    _inherit = 'om.inventory.report.slow_moving'

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        columns.insert(1, value_column(self.env))
        return columns

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        start, end = self._om_period_bounds(options)
        return self._om_set_values(rows, end, [('closing', 'value')], options)

    @api.model
    def _om_get_kpis(self, data, options):
        kpis = super()._om_get_kpis(data, options)
        dead = [r for r in data['all_rows'] if r['status_id'] == 'dead']
        slow = [r for r in data['all_rows'] if r['status_id'] == 'slow']
        kpis = [k for k in kpis if k['key'] != 'dead_qty']
        kpis.append({'key': 'dead_value', 'label': self.env._("Value of dead stock"),
                     'value': sum(r['value'] for r in dead), 'type': 'monetary', 'icon': 'payments',
                     'tone': 'danger' if dead else 'success', 'filter': 'dead'})
        kpis.append({'key': 'slow_value', 'label': self.env._("Value of slow stock"),
                     'value': sum(r['value'] for r in slow), 'type': 'monetary', 'icon': 'payments',
                     'tone': 'warning' if slow else 'success', 'filter': 'slow'})
        return kpis


class OmInventoryReportAbc(models.AbstractModel):
    _inherit = 'om.inventory.report.abc'

    @api.model
    def _om_abc_costs(self, product_ids, options):
        # the cost of the period's end, from the stock valuation
        start, end = self._om_period_bounds(options)
        costs = self._om_unit_costs(product_ids, end, options)
        company = self.env.company.id
        return {product_id: costs.get((company, product_id), 0.0) for product_id in product_ids}


class OmInventoryReportTurnover(models.AbstractModel):
    _inherit = 'om.inventory.report.turnover'

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        columns.insert(2, value_column(self.env, 'closing_value', self.env._("Closing Value"), visible=False))
        return columns

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        start, end = self._om_period_bounds(options)
        return self._om_set_values(rows, end, [('closing', 'closing_value')], options)


class OmInventoryReportAdjustments(models.AbstractModel):
    _inherit = 'om.inventory.report.adjustments'

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        columns.insert(len(columns) - 1, {
            **value_column(self.env, 'net_value', self.env._("Net Value")),
            'help': self.env._("Net quantity at the unit cost of the end of the period."),
        })
        return columns

    @api.model
    def _om_get_rows(self, options):
        rows = super()._om_get_rows(options)
        start, end = self._om_period_bounds(options)
        return self._om_set_values(rows, end, [('net', 'net_value')], options)

    @api.model
    def _om_get_kpis(self, data, options):
        kpis = super()._om_get_kpis(data, options)
        kpis.insert(4, {'key': 'net_value', 'label': self.env._("Net value"),
                        'value': data['total']['values'].get('net_value', 0.0), 'type': 'monetary',
                        'icon': 'payments'})
        return kpis
