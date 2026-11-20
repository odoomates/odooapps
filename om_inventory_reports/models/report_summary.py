from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL
from odoo.tools.translate import LazyTranslate

from .report_moves import DIM_COLUMNS, IN_KINDS, OUT_KINDS

_lt = LazyTranslate(__name__)

# the periods the summary can be grouped by, each a dimension of its own
PERIODS = ('day', 'week', 'month')
# a line per product and period at most: a finer period or a shorter range above
MAX_PERIOD_ROWS = 150000


class OmInventoryReportSummary(models.AbstractModel):
    """Opening, what came in and went out by kind of movement, closing."""
    _name = 'om.inventory.report.summary'
    _inherit = 'om.inventory.report'
    _description = 'Inventory Summary Report'

    _report_key = 'summary'
    _report_name = _lt('Inventory Summary')
    _report_section = 'movement'
    _report_sequence = 30
    _report_icon = 'table_chart'
    _report_description = _lt('Opening, receipts and issues by kind, closing, for a period.')
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot', 'owner')
    _report_group_by = ('category', 'product', 'warehouse', 'location', 'lot', 'owner') + PERIODS
    _report_default_group_by = ('category', 'product')
    _report_bar_column = 'closing'
    _report_compare_keys = ('qty_in', 'qty_out', 'closing')

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        dimensions['day'] = {'label': self.env._("Day"), 'icon': 'calendar_today'}
        dimensions['week'] = {'label': self.env._("Week"), 'icon': 'calendar_today'}
        dimensions['month'] = {'label': self.env._("Month"), 'icon': 'calendar_today'}
        return dimensions

    @api.model
    def _om_grain(self, options):
        """The period the report is grouped by (day, week, month), if any."""
        return next((g for g in options['group_by'] if g in PERIODS), None)

    @api.model
    def _om_normalize_options(self, options):
        options = super()._om_normalize_options(options)
        periods = [g for g in options['group_by'] if g in PERIODS]
        if len(periods) > 1:
            # one period at a time: a month split in days says nothing a day does not
            options['group_by'] = [g for g in options['group_by'] if g not in PERIODS or g == periods[0]]
        if periods:
            # each period is compared with the one before it already
            options['compare'] = False
        return options

    @api.model
    def _om_names(self, dim, ids):
        if dim not in PERIODS:
            return super()._om_names(dim, ids)
        lang = self.env['res.lang']._get_data(code=self.env.lang or 'en_US')
        fmt = lang.date_format if lang else '%m/%d/%Y'
        names = {}
        for key in ids:
            day = fields.Date.to_date(key)
            if dim == 'day':
                names[key] = '%s %s' % (day.strftime('%a'), day.strftime(fmt))
            elif dim == 'week':
                year, week, _weekday = day.isocalendar()
                names[key] = self.env._("Week %(week)s, %(year)s (from %(start)s)",
                                        week=week, year=year, start=day.strftime(fmt))
            else:
                names[key] = day.strftime('%B %Y')
        return names

    @api.model
    def _om_sort_nodes(self, nodes, options):
        super()._om_sort_nodes(nodes, options)
        sort = options.get('sort') or {}
        if not sort.get('key') or sort.get('key') == 'name':
            # periods in time order, not by their name
            stack = [nodes]
            while stack:
                level = stack.pop()
                if level and level[0]['dim'] in PERIODS:
                    level.sort(key=lambda n: n['res_id'] or '', reverse=sort.get('dir') == 'desc')
                stack.extend(node['children'] for node in level)

    @api.model
    def _om_get_columns(self, options):
        labels = self._om_kind_labels()
        internal = self._om_count_internal(options)
        columns = [{'key': 'opening', 'label': self.env._("Opening"), 'type': 'float', 'aggregate': 'sum'}]
        for kind in IN_KINDS:
            if kind == 'in_internal' and not internal:
                continue
            columns.append({'key': kind, 'label': labels[kind], 'type': 'float', 'aggregate': 'sum',
                            'visible': False, 'group': 'in'})
        columns.append({'key': 'qty_in', 'label': self.env._("Total In"), 'type': 'float', 'aggregate': 'sum'})
        for kind in OUT_KINDS:
            if kind == 'out_internal' and not internal:
                continue
            columns.append({'key': kind, 'label': labels[kind], 'type': 'float', 'aggregate': 'sum',
                            'visible': False, 'group': 'out'})
        columns += [
            {'key': 'qty_out', 'label': self.env._("Total Out"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'closing', 'label': self.env._("Closing"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]
        # the main kinds are shown by default
        for column in columns:
            if column['key'] in ('in_purchase', 'in_production', 'out_sale', 'out_production', 'out_scrap'):
                column['visible'] = True
        return columns

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        period = self._om_grain(options)
        if period:
            return self._om_period_rows(options, period, start, end)
        return self._om_move_balances(options, start, end)

    @api.model
    def _om_period_starts(self, options, period):
        """The first day of each period from the start of the range to its end."""
        date_from = fields.Date.to_date(options['date_from'])
        date_to = fields.Date.to_date(options['date_to'])
        if period == 'day':
            current, step = date_from, relativedelta(days=1)
        elif period == 'week':
            current, step = date_from - timedelta(days=date_from.weekday()), relativedelta(weeks=1)
        else:
            current, step = date_from.replace(day=1), relativedelta(months=1)
        starts = []
        while current <= date_to:
            starts.append(current)
            current += step
        return starts

    @api.model
    def _om_period_rows(self, options, period, start, end):
        """A line per product (and location, lot, owner) and period, each with
        its own opening and closing: the closing of a period is the opening of
        the next. Every product of the range has a line in every period, moved
        or not, so that a period's opening and closing count all the stock."""
        dims = self._om_row_dimensions(options) - set(PERIODS)
        keys = [DIM_COLUMNS[d] for d in DIM_COLUMNS if d in dims]
        balances = self._om_move_balances(options, start, end, dims=dims)
        starts = self._om_period_starts(options, period)
        if len(balances) * len(starts) > MAX_PERIOD_ROWS:
            raise UserError(self.env._(
                "Too many lines: %(products)s products over %(periods)s periods. Group by a longer period, "
                "or choose a shorter range or fewer products.", products=len(balances), periods=len(starts)))
        location_ids = self._om_location_ids(options)
        sides = self._om_move_sides(options, location_ids, end)
        tz = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        kind_sums = [
            SQL("COALESCE(SUM(%s) FILTER (WHERE s.kind = %s), 0) AS %s",
                SQL("s.qty") if kind.startswith('in') else SQL("-s.qty"), kind, SQL.identifier(kind))
            for kind in IN_KINDS + OUT_KINDS
        ]
        group = SQL(", ").join(SQL.identifier('s', k) for k in keys)
        self.env.cr.execute(SQL("""
            SELECT %(group)s,
                   DATE_TRUNC(%(unit)s, (s.date AT TIME ZONE 'UTC') AT TIME ZONE %(tz)s)::date AS period_start,
                   %(kinds)s
              FROM (%(sides)s) s
             WHERE s.date >= %(start)s
          GROUP BY %(group)s, period_start
        """, group=group, unit=period, tz=tz, kinds=SQL(", ").join(kind_sums), sides=sides, start=start))
        moved = {}
        for row in self.env.cr.dictfetchall():
            moved[tuple(row[k] for k in keys) + (row['period_start'],)] = row
        rows = []
        for balance in balances:
            key = tuple(balance[k] for k in keys)
            running = balance['opening']
            for period_start in starts:
                movement = moved.get(key + (period_start,), {})
                row = {k: balance[k] for k in keys}
                row[period + '_id'] = fields.Date.to_string(period_start)
                row['_period'] = period_start
                row['opening'] = running
                for kind in IN_KINDS + OUT_KINDS:
                    row[kind] = movement.get(kind, 0.0)
                row['qty_in'] = sum(row[k] for k in IN_KINDS)
                row['qty_out'] = sum(row[k] for k in OUT_KINDS)
                row['closing'] = running + row['qty_in'] - row['qty_out']
                running = row['closing']
                rows.append(row)
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        rows = node['rows']
        if rows and '_period' in rows[0]:
            # a group over several periods opens with the first and closes with the last
            first = min(r['_period'] for r in rows)
            last = max(r['_period'] for r in rows)
            if first != last:
                node['values']['opening'] = sum(r['opening'] for r in rows if r['_period'] == first)
                node['values']['closing'] = sum(r['closing'] for r in rows if r['_period'] == last)

    @api.model
    def _om_get_kpis(self, data, options):
        total = data['total']['values']
        rows = data['rows']
        return [
            {'key': 'opening', 'label': self.env._("Opening"), 'value': total.get('opening', 0), 'type': 'float',
             'icon': 'history'},
            {'key': 'qty_in', 'label': self.env._("Total in"), 'value': total.get('qty_in', 0), 'type': 'float',
             'icon': 'south_east', 'tone': 'success'},
            {'key': 'qty_out', 'label': self.env._("Total out"), 'value': total.get('qty_out', 0),
             'type': 'float', 'icon': 'north_east', 'tone': 'danger'},
            {'key': 'closing', 'label': self.env._("Closing"), 'value': total.get('closing', 0), 'type': 'float',
             'icon': 'inventory_2'},
            {'key': 'no_move', 'label': self.env._("Products not moved"),
             'value': len(self._om_not_moved(rows)), 'type': 'int',
             'icon': 'hourglass_empty', 'tone': 'warning', 'filter': 'no_move'},
        ]

    @api.model
    def _om_not_moved(self, rows):
        """The products with nothing in or out over the whole range, in any period."""
        moved = {r['product_id'] for r in rows if r['qty_in'] or r['qty_out']}
        return {r['product_id'] for r in rows} - moved

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'no_move':
            idle = self._om_not_moved(rows)
            return [r for r in rows if r['product_id'] in idle]
        return rows
