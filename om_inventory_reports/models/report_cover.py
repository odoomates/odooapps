from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import SQL
from odoo.tools.translate import LazyTranslate

from .report_slow_moving import USE_KINDS

_lt = LazyTranslate(__name__)

# the period the pace of use is measured on, by default
DEFAULT_PACE_DAYS = 90


class OmInventoryReportCover(models.AbstractModel):
    """What the stock-out forecast and the overstock report share: the stock at
    the end of the period, what was used during it, the pace of use per day,
    and how many days the stock lasts at that pace.

    Not a report of its own: it has no key, so it is not in the catalog.
    """
    _name = 'om.inventory.report.cover'
    _inherit = 'om.inventory.report'
    _description = 'Days of Cover (shared)'

    _report_section = 'analysis'
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('status', 'category', 'product', 'warehouse', 'location')
    _report_default_group_by = ('status', 'product')
    _report_date_mode = 'range'
    _report_expand_default = True

    @api.model
    def _om_default_options(self):
        # the last three months: recent enough to be today's pace, long enough
        # not to swing on one big order
        options = super()._om_default_options()
        today = fields.Date.context_today(self)
        options.update({
            'date_preset': 'custom',
            'date_from': fields.Date.to_string(today - timedelta(days=DEFAULT_PACE_DAYS - 1)),
            'date_to': fields.Date.to_string(today),
        })
        return options

    @api.model
    def _om_row_dimensions(self, options):
        dims = set(options['group_by']) - {'status'} | {'product'}
        if 'warehouse' in dims:
            dims.add('location')
        return dims

    @api.model
    def _om_days(self, options):
        days = (fields.Date.to_date(options['date_to']) - fields.Date.to_date(options['date_from'])).days + 1
        return max(days, 1)

    @api.model
    def _om_incoming(self, options, dims):
        """Quantities still to come into the report's locations: receipts and
        transfers that are planned but not done, in the product's unit."""
        location_ids = self._om_location_ids(options)
        if not location_ids:
            return {}
        conditions = [
            SQL("sm.state IN ('waiting', 'confirmed', 'partially_available', 'assigned')"),
            SQL("sm.company_id = ANY(%s)", self.env.companies.ids),
            SQL("sm.location_dest_id = ANY(%s)", location_ids),
            SQL("NOT (sm.location_id = ANY(%s))", location_ids),
        ]
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            conditions.append(SQL("sm.product_id = ANY(%s)", product_ids))
        by_location = 'location' in dims
        group = SQL("sm.product_id, sm.location_dest_id") if by_location else SQL("sm.product_id")
        self.env.cr.execute(SQL("""
            SELECT %(group)s, SUM(sm.product_qty) AS qty
              FROM stock_move sm
             WHERE %(where)s
          GROUP BY %(group)s
        """, group=group, where=SQL(" AND ").join(conditions)))
        result = {}
        for row in self.env.cr.dictfetchall():
            key = (row['product_id'], row['location_dest_id']) if by_location else (row['product_id'],)
            result[key] = row['qty']
        return result

    @api.model
    def _om_cover_rows(self, options):
        """The rows with closing, used, incoming, daily use and days of cover."""
        start, end = self._om_period_bounds(options)
        rows = self._om_move_balances(options, start, end)
        dims = self._om_row_dimensions(options)
        incoming = self._om_incoming(options, dims)
        by_location = 'location' in dims
        days = self._om_days(options)
        seen = set()
        for row in rows:
            key = (row['product_id'], row.get('location_id')) if by_location else (row['product_id'],)
            seen.add(key)
            row['incoming'] = incoming.get(key, 0.0)
        # products with nothing in stock and nothing moved yet, only on order
        for key, qty in incoming.items():
            if key not in seen:
                row = {'product_id': key[0], 'opening': 0.0, 'closing': 0.0, 'incoming': qty,
                       **{kind: 0.0 for kind in USE_KINDS}}
                if by_location:
                    row['location_id'] = key[1]
                rows.append(row)
        for row in rows:
            row['issued'] = sum(row.get(k) or 0.0 for k in USE_KINDS)
            row['daily'] = row['issued'] / days
            row['cover'] = max(row['closing'], 0.0) / row['daily'] if row['daily'] > 0 else False
        return rows

    @api.model
    def _om_cover_node(self, node, options):
        """Pace and cover of a group, from its sums: a sum of covers means nothing."""
        values = node['values']
        values['daily'] = (values.get('issued') or 0.0) / self._om_days(options)
        values['cover'] = max(values.get('closing') or 0.0, 0.0) / values['daily'] if values['daily'] > 0 else False

    @api.model
    def _om_toggles(self):
        toggles = [t for t in super()._om_toggles() if t['key'] != 'hide_zero']
        return toggles


class OmInventoryReportStockout(models.AbstractModel):
    """Products about to run out: how many days the stock lasts at the pace of
    the period, the day it runs out, and what it takes to last the horizon."""
    _name = 'om.inventory.report.stockout'
    _inherit = 'om.inventory.report.cover'
    _description = 'Stock-out Forecast Report'

    _report_key = 'stockout'
    _report_overview = 5
    _report_name = _lt('Stock-out Forecast')
    _report_sequence = 47
    _report_section = 'stock'
    _report_icon = 'event_busy'
    _report_description = _lt('Products that run out soon at the pace they are used: days of cover and '
                              'stock-out date.')
    _report_extra_options = {'horizon_days': 30, 'count_incoming': True, 'only_at_risk': True}
    _report_bar_column = 'cover'

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['status'] = {
            'label': self.env._("Status"),
            'icon': 'event_busy',
            'selection': {
                'out': self.env._("Out of stock"),
                'soon': self.env._("Runs out within the horizon"),
                'later': self.env._("Lasts beyond the horizon"),
            },
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'closing', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'incoming', 'label': self.env._("Incoming"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("Receipts and transfers planned into these locations, not done yet.")},
            {'key': 'issued', 'label': self.env._("Used in Period"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("Delivered to customers and consumed in production during the period.")},
            {'key': 'daily', 'label': self.env._("Daily Use"), 'type': 'ratio',
             'help': self.env._("Used in the period / days of the period.")},
            {'key': 'cover', 'label': self.env._("Days of Cover"), 'type': 'days', 'optional': False,
             'help': self.env._("How many days the stock lasts at the period's pace.")},
            {'key': 'stockout_date', 'label': self.env._("Runs Out On"), 'type': 'date'},
            {'key': 'to_cover', 'label': self.env._("Short for Horizon"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("What is missing to last the horizon at the period's pace.")},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_get_rows(self, options):
        horizon = int(options.get('horizon_days') or 30)
        count_incoming = options.get('count_incoming')
        end_day = fields.Date.to_date(options['date_to'])
        rows = []
        for row in self._om_cover_rows(options):
            if row['daily'] <= 0:
                continue  # not used in the period: nothing to forecast
            stock = max(row['closing'], 0.0) + (row['incoming'] if count_incoming else 0.0)
            row['cover'] = stock / row['daily']
            if stock <= 0:
                row['status_id'] = 'out'
            elif row['cover'] <= horizon:
                row['status_id'] = 'soon'
            else:
                row['status_id'] = 'later'
            if options.get('only_at_risk') and row['status_id'] == 'later':
                continue
            row['stockout_date'] = end_day + timedelta(days=int(row['cover']))
            row['to_cover'] = max(row['daily'] * horizon - stock, 0.0)
            rows.append(row)
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        values = node['values']
        values['daily'] = values.get('issued', 0.0) / self._om_days(options)
        stock = max(values.get('closing') or 0.0, 0.0)
        if options.get('count_incoming'):
            stock += values.get('incoming') or 0.0
        values['cover'] = stock / values['daily'] if values['daily'] > 0 else False
        dates = [r['stockout_date'] for r in node['rows'] if r.get('stockout_date')]
        values['stockout_date'] = min(dates) if dates else False
        statuses = {r['status_id'] for r in node['rows']}
        if 'out' in statuses:
            values['cover_tone'] = 'danger'
        elif 'soon' in statuses:
            values['cover_tone'] = 'warning'

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options['kpi_filter']:
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_toggles(self):
        return [
            {'key': 'count_incoming', 'label': self.env._("Count incoming receipts")},
            {'key': 'only_at_risk', 'label': self.env._("Only products at risk")},
        ] + super()._om_toggles()

    @api.model
    def _om_extra_options_meta(self, options):
        return [{'key': 'horizon_days', 'label': self.env._("Horizon (days)"), 'min': 1, 'step': 1}]

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        out = {r['product_id'] for r in rows if r['status_id'] == 'out'}
        soon = {r['product_id'] for r in rows if r['status_id'] == 'soon'} - out
        horizon = int(options.get('horizon_days') or 30)
        return [
            {'key': 'out', 'label': self.env._("Out of stock"), 'value': len(out), 'type': 'int',
             'icon': 'block', 'tone': 'danger' if out else 'success', 'filter': 'out'},
            {'key': 'soon', 'label': self.env._("Run out within %s days", horizon), 'value': len(soon),
             'type': 'int', 'icon': 'hourglass_bottom', 'tone': 'warning' if soon else 'success', 'filter': 'soon'},
            {'key': 'to_cover', 'label': self.env._("Units short for the horizon"),
             'value': sum(r['to_cover'] for r in rows), 'type': 'float', 'icon': 'add_shopping_cart'},
            {'key': 'pace', 'label': self.env._("Pace measured over"), 'value': self._om_days(options),
             'type': 'days', 'icon': 'calendar_today'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi in ('out', 'soon'):
            return [r for r in rows if r['status_id'] == kpi]
        return rows

    @api.model
    def _om_get_chart(self, data, options):
        horizon = int(options.get('horizon_days') or 30)
        # the products still in stock: those already out are a key figure
        covers = {}
        for row in data['rows']:
            if row['status_id'] == 'out':
                continue
            product = row['product_id']
            covers[product] = min(covers.get(product, row['cover']), row['cover'])
        soonest = sorted(covers.items(), key=lambda item: item[1])[:10]
        if not soonest:
            return None
        names = self._om_names('product', [p for p, _c in soonest])
        return {
            'type': 'bar',
            'title': self.env._("Next to run out (days of cover)"),
            'value_type': 'days',
            'items': [{
                'key': str(product), 'label': names.get(product, ''), 'value': cover,
                'tone': 'danger' if cover <= 0 else 'warning' if cover <= horizon else 'info',
            } for product, cover in soonest],
        }

    @api.model
    def _om_link_targets(self):
        labels = {
            'stock_card': self.env._("Open Stock Card"),
            'reorder': self.env._("Open Reorder Report"),
        }
        return list(labels.items())


class OmInventoryReportOverstock(models.AbstractModel):
    """Stock beyond what the pace of use needs: the excess over a number of
    days of cover, and its value against the whole stock."""
    _name = 'om.inventory.report.overstock'
    _inherit = 'om.inventory.report.cover'
    _description = 'Overstock Report'

    _report_key = 'overstock'
    _report_overview = 6
    _report_name = _lt('Overstock')
    _report_sequence = 57
    _report_icon = 'inventory_2'
    _report_description = _lt('Stock beyond what the pace of use needs: excess quantity and value.')
    _report_extra_options = {'max_days': 180, 'only_excess': True}
    _report_bar_column = 'excess_value'

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['status'] = {
            'label': self.env._("Status"),
            'icon': 'inventory_2',
            'selection': {
                'unused': self.env._("In stock, not used in the period"),
                'excess': self.env._("More than the days of cover allowed"),
                'ok': self.env._("Within the days of cover"),
            },
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'closing', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'issued', 'label': self.env._("Used in Period"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("Delivered to customers and consumed in production during the period.")},
            {'key': 'cover', 'label': self.env._("Days of Cover"), 'type': 'days',
             'help': self.env._("How many days the stock lasts at the period's pace.")},
            {'key': 'excess', 'label': self.env._("Excess"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("On hand beyond the days of cover allowed; all of it when not used.")},
            {'key': 'value', 'label': self.env._("Stock Value"), 'type': 'monetary', 'aggregate': 'sum',
             'visible': False},
            {'key': 'excess_value', 'label': self.env._("Excess Value"), 'type': 'monetary', 'aggregate': 'sum',
             'optional': False},
            {'key': 'share', 'label': self.env._("Share of Stock Value"), 'type': 'percent', 'aggregate': 'sum',
             'help': self.env._("Excess value / value of all the stock in these locations.")},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_get_rows(self, options):
        max_days = float(options.get('max_days') or 180)
        rows = [r for r in self._om_cover_rows(options) if r['closing'] > 0]
        costs = self._om_product_costs([r['product_id'] for r in rows], options)
        for row in rows:
            cost = costs.get(row['product_id'], 0.0)
            row['unit_cost'] = cost
            row['value'] = row['closing'] * cost
            if row['daily'] <= 0:
                row['status_id'] = 'unused'
                row['excess'] = row['closing']
            else:
                row['excess'] = max(row['closing'] - row['daily'] * max_days, 0.0)
                row['status_id'] = 'excess' if row['excess'] > 0 else 'ok'
            row['excess_value'] = row['excess'] * cost
        total = sum(r['value'] for r in rows)
        for row in rows:
            row['share'] = row['excess_value'] / total * 100 if total else 0.0
        if options.get('only_excess'):
            rows = [r for r in rows if r['status_id'] != 'ok']
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        self._om_cover_node(node, options)
        statuses = {r['status_id'] for r in node['rows']}
        if 'unused' in statuses:
            node['values']['excess_tone'] = 'danger'
        elif 'excess' in statuses:
            node['values']['excess_tone'] = 'warning'

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options['kpi_filter']:
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_toggles(self):
        return [{'key': 'only_excess', 'label': self.env._("Only products in excess")}] + \
            super()._om_toggles()

    @api.model
    def _om_extra_options_meta(self, options):
        return [{'key': 'max_days', 'label': self.env._("Days of cover allowed"), 'min': 1, 'step': 1}]

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        unused = [r for r in rows if r['status_id'] == 'unused']
        excess = [r for r in rows if r['status_id'] == 'excess']
        return [
            {'key': 'excess_value', 'label': self.env._("Excess value"),
             'value': sum(r['excess_value'] for r in rows), 'type': 'monetary', 'icon': 'payments',
             'tone': 'warning' if unused or excess else 'success'},
            {'key': 'share', 'label': self.env._("Share of stock value"),
             'value': sum(r['share'] for r in rows), 'type': 'percent', 'icon': 'pie_chart'},
            {'key': 'excess', 'label': self.env._("Products in excess"),
             'value': len({r['product_id'] for r in excess}), 'type': 'int', 'icon': 'inventory_2',
             'tone': 'warning' if excess else 'success', 'filter': 'excess'},
            {'key': 'unused', 'label': self.env._("In stock, not used"),
             'value': len({r['product_id'] for r in unused}), 'type': 'int', 'icon': 'block',
             'tone': 'danger' if unused else 'success', 'filter': 'unused'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi in ('excess', 'unused'):
            return [r for r in rows if r['status_id'] == kpi]
        return rows

    @api.model
    def _om_get_chart(self, data, options):
        items = self._om_top_items(data['rows'], 'excess_value', tone='warning')
        if not items:
            return None
        return {'type': 'bar', 'title': self.env._("Largest excess value"), 'value_type': 'monetary',
                'items': items}
