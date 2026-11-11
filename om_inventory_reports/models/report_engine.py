import json
import threading
import time as clock
from collections import OrderedDict, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


# Children sent per request; the screen asks for the next page with "Show more"
PAGE_SIZE = 200
# Rows written to a PDF or Excel file at most
EXPORT_LIMIT = 100000

# A computed report is kept a short while, by user, companies and options, so
# that unfolding a group or showing more lines does not compute it again
CACHE_SIZE = 16
CACHE_SECONDS = 120
_cache = OrderedDict()
_cache_lock = threading.Lock()

# the reports summed up on the overview, in this order
OVERVIEW_REPORTS = (
    'stock_on_hand', 'valuation', 'negative', 'reorder', 'slow_moving', 'ageing', 'transfers', 'adjustments',
    'expiry',
)

DATE_PRESETS = (
    'today', 'yesterday', 'this_week', 'this_month', 'this_quarter', 'this_year',
    'last_week', 'last_month', 'last_quarter', 'last_year', 'custom',
)


class OmInventoryReport(models.AbstractModel):
    """The engine of the inventory reports.

    Every report is an abstract model inheriting this one. A report says what it
    is (the ``_report_*`` attributes), which columns it has, and gives its rows:
    plain dicts with the ids of the dimensions (product, location, ...) and the
    measures. The engine filters the rows, builds the groups the user asked for,
    sums the measures, sorts, pages, and serves the same lines to the screen,
    the PDF and the Excel file, so the three always agree.

    A line sent to the screen::

        {'id': 'category-4|product-12', 'parent_id': 'category-4', 'level': 1,
         'kind': 'group' | 'leaf' | 'detail' | 'total', 'name': '[FURN_001] Chair',
         'values': {column key: value}, 'has_children': True,
         'open': {'res_model': 'product.product', 'res_id': 12},
         'links': [{'report': 'stock_card', 'label': 'Stock Card', 'options': {...}}]}
    """
    _name = 'om.inventory.report'
    _description = 'Inventory Report'

    # what a report is; a report model sets at least _report_key and _report_name
    _report_key = None
    _report_name = ''
    _report_section = 'stock'
    _report_sequence = 100
    _report_icon = 'table'
    _report_description = ''
    # 'range' (from - to), 'as_of' (one date, today by default) or 'none'
    _report_date_mode = 'range'
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('category', 'product', 'warehouse', 'location')
    _report_default_group_by = ('category', 'product')
    # options of the report beyond the common ones, with their default
    _report_extra_options = {}
    # leaves have detail lines (moves, quants), loaded when unfolded
    _report_has_details = False
    # this report's lines are best read with every group unfolded
    _report_expand_default = False
    # columns that can be compared with an earlier period (sums only)
    _report_compare_keys = ()
    # the main column, drawn with a bar in each cell to compare the lines at a glance
    _report_bar_column = None

    # ------------------------------------------------------------------
    # Report catalog
    # ------------------------------------------------------------------

    @api.model
    def _om_report_models(self):
        reports = []
        for name in self.env.registry:
            if not name.startswith('om.inventory.report.'):
                continue
            report = self.env[name]
            if getattr(report, '_report_key', None) and report._om_report_available():
                reports.append(report)
        return sorted(reports, key=lambda r: (r._report_sequence, r._report_name))

    @api.model
    def _om_report(self, key):
        for report in self._om_report_models():
            if report._report_key == key:
                return report
        raise UserError(self.env._("This report does not exist: %s", key))

    @api.model
    def _om_report_available(self):
        return True

    @api.model
    def _om_sections(self):
        return {
            'stock': self.env._("Stock"),
            'movement': self.env._("Movements"),
            'valuation': self.env._("Valuation"),
            'analysis': self.env._("Analysis"),
            'operations': self.env._("Operations"),
        }

    @api.model
    def om_get_catalog(self):
        """The reports of the switcher, by section."""
        self._om_check_access()
        sections = self._om_sections()
        overview = {
            'key': 'overview',
            'name': self.env._("Overview"),
            'description': self.env._("Key figures of every report, at a glance."),
            'icon': 'grid_view',
            'section': 'overview',
            'section_name': self.env._("Overview"),
            'model': self._name,
        }
        return [overview] + [{
            'key': report._report_key,
            'name': report._om_report_title(),
            'description': str(report._report_description or ''),
            'icon': report._report_icon,
            'section': report._report_section,
            'section_name': sections.get(report._report_section, report._report_section),
            'model': report._name,
        } for report in self._om_report_models()]

    def _om_report_title(self):
        return str(self._report_name)

    @api.model
    def om_get_overview(self):
        """A card per report with its key figures, as the report opens by default."""
        self._om_check_access()
        cards = []
        for key in OVERVIEW_REPORTS:
            try:
                report = self._om_report(key)
            except UserError:
                continue
            options = report._om_normalize_options({})
            data = report._om_compute(options)
            cards.append({
                'key': key,
                'name': report._om_report_title(),
                'icon': report._report_icon,
                'description': str(report._report_description or ''),
                'subtitle': report._om_subtitle(options),
                'kpis': report._om_get_kpis(data, options)[:4],
            })
        return {
            'cards': cards,
            'currency_id': self.env.company.currency_id.id,
            'digits': self._om_digits(),
        }

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @api.model
    def _om_check_access(self):
        if not self.env.user.has_group('stock.group_stock_user'):
            raise AccessError(self.env._("Only Inventory users can open the inventory reports."))

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    @api.model
    def _om_default_options(self):
        options = {
            'date_preset': 'this_month' if self._report_date_mode == 'range' else 'today',
            'date_from': False,
            'date_to': False,
            'warehouse_ids': [],
            'location_ids': [],
            'product_ids': [],
            'category_ids': [],
            'lot_ids': [],
            'owner_ids': [],
            'partner_ids': [],
            'picking_type_ids': [],
            'child_locations': True,
            'hide_zero': True,
            'group_by': list(self._report_default_group_by),
            'columns': False,
            'sort': False,
            'search': '',
            'kpi_filter': False,
            'compare': False,
        }
        options.update(self._report_extra_options)
        return options

    @api.model
    def _om_normalize_options(self, options):
        defaults = self._om_default_options()
        options = {**defaults, **{k: v for k, v in (options or {}).items() if k in defaults}}
        for key in ('warehouse_ids', 'location_ids', 'product_ids', 'category_ids', 'lot_ids',
                    'owner_ids', 'partner_ids', 'picking_type_ids'):
            options[key] = [int(i) for i in options[key] or [] if str(i).isdigit()]
        group_by = [g for g in options['group_by'] or [] if g in self._report_group_by]
        options['group_by'] = list(dict.fromkeys(group_by))[:3] or list(self._report_default_group_by)
        if options['date_preset'] not in DATE_PRESETS:
            options['date_preset'] = defaults['date_preset']
        date_from, date_to = self._om_preset_dates(options)
        options['date_from'] = date_from and fields.Date.to_string(date_from)
        options['date_to'] = date_to and fields.Date.to_string(date_to)
        if self._report_date_mode == 'none':
            options['date_from'] = options['date_to'] = False
        options['search'] = (options['search'] or '').strip()
        if options['compare'] not in ('previous_period', 'previous_year') or not self._report_compare_keys \
                or self._report_date_mode == 'none':
            options['compare'] = False
        return options

    @api.model
    def _om_compare_options(self, options):
        """The options of the period compared with: the one before, or a year earlier."""
        date_to = fields.Date.to_date(options['date_to'])
        date_from = fields.Date.to_date(options['date_from']) if options.get('date_from') else False
        if options['compare'] == 'previous_year':
            shift = relativedelta(years=1)
            new_from, new_to = date_from and date_from - shift, date_to - shift
        elif self._report_date_mode == 'as_of':
            # the end of the month before, or the day a month earlier
            last_of_month = date_to + relativedelta(days=1) == (date_to + relativedelta(days=1)).replace(day=1)
            new_to = date_to.replace(day=1) - relativedelta(days=1) if last_of_month else date_to - relativedelta(months=1)
            new_from = False
        else:
            months = next((n for n in (1, 3, 12) if date_from.day == 1
                           and date_from + relativedelta(months=n, days=-1) == date_to), 0)
            if months:
                new_from = date_from - relativedelta(months=months)
                new_to = date_from - relativedelta(days=1)
            else:
                length = (date_to - date_from).days + 1
                new_from, new_to = date_from - timedelta(days=length), date_from - timedelta(days=1)
        return {**options, 'date_preset': 'custom', 'compare': False, 'kpi_filter': False, 'search': '',
                'date_from': new_from and fields.Date.to_string(new_from), 'date_to': fields.Date.to_string(new_to)}

    @api.model
    def _om_compare_label(self, options):
        if not options.get('compare'):
            return ''
        return self._om_subtitle(self._om_compare_options(options))

    @api.model
    def _om_preset_dates(self, options):
        """(date_from, date_to) of the period; date_from is False for 'as of' reports."""
        today = fields.Date.context_today(self)
        preset = options['date_preset']
        if preset == 'custom':
            date_to = fields.Date.to_date(options.get('date_to')) or today
            date_from = fields.Date.to_date(options.get('date_from')) or date_to.replace(day=1)
            if date_from > date_to:
                date_from, date_to = date_to, date_from
        elif preset == 'today':
            date_from = date_to = today
        elif preset == 'yesterday':
            date_from = date_to = today - timedelta(days=1)
        elif preset in ('this_week', 'last_week'):
            date_from = today - timedelta(days=today.weekday())
            if preset == 'last_week':
                date_from -= timedelta(days=7)
            date_to = date_from + timedelta(days=6)
        elif preset in ('this_month', 'last_month'):
            date_from = today.replace(day=1)
            if preset == 'last_month':
                date_from -= relativedelta(months=1)
            date_to = date_from + relativedelta(months=1, days=-1)
        elif preset in ('this_quarter', 'last_quarter'):
            date_from = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
            if preset == 'last_quarter':
                date_from -= relativedelta(months=3)
            date_to = date_from + relativedelta(months=3, days=-1)
        else:  # this_year, last_year
            date_from = date(today.year - (preset == 'last_year'), 1, 1)
            date_to = date(date_from.year, 12, 31)
        if self._report_date_mode == 'as_of':
            return False, date_to
        return date_from, date_to

    @api.model
    def _om_datetime_end(self, day):
        """The last instant of ``day`` in the user's time zone, as a naive UTC datetime."""
        return self._om_datetime_start(day + timedelta(days=1))

    @api.model
    def _om_datetime_start(self, day):
        """The first instant of ``day`` in the user's time zone, as a naive UTC datetime."""
        local = datetime.combine(fields.Date.to_date(day), time.min)
        try:
            tz = ZoneInfo(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        except (ZoneInfoNotFoundError, ValueError):
            tz = timezone.utc
        return local.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)

    @api.model
    def _om_is_today(self, options):
        return not options['date_to'] or fields.Date.to_date(options['date_to']) >= fields.Date.context_today(self)

    # ------------------------------------------------------------------
    # Filters, dimensions, columns
    # ------------------------------------------------------------------

    @api.model
    def _om_filter_definitions(self):
        companies = self.env.companies.ids
        return {
            'warehouse': {'label': self.env._("Warehouse"), 'model': 'stock.warehouse', 'icon': 'storefront',
                          'option': 'warehouse_ids', 'domain': [('company_id', 'in', companies)]},
            'location': {'label': self.env._("Location"), 'model': 'stock.location', 'icon': 'location_on',
                         'option': 'location_ids',
                         'domain': [('usage', 'in', ('internal', 'view')), ('company_id', 'in', companies + [False])]},
            'product': {'label': self.env._("Product"), 'model': 'product.product', 'icon': 'package_2',
                        'option': 'product_ids', 'domain': [('is_storable', '=', True)]},
            'category': {'label': self.env._("Category"), 'model': 'product.category', 'icon': 'sell',
                         'option': 'category_ids', 'domain': []},
            'lot': {'label': self.env._("Lot/Serial"), 'model': 'stock.lot', 'icon': 'barcode',
                    'option': 'lot_ids', 'domain': [('company_id', 'in', companies + [False])]},
            'owner': {'label': self.env._("Owner"), 'model': 'res.partner', 'icon': 'person',
                      'option': 'owner_ids', 'domain': []},
            'partner': {'label': self.env._("Partner"), 'model': 'res.partner', 'icon': 'person',
                        'option': 'partner_ids', 'domain': []},
            'picking_type': {'label': self.env._("Operation Type"), 'model': 'stock.picking.type',
                             'icon': 'local_shipping', 'option': 'picking_type_ids',
                             'domain': [('company_id', 'in', companies)]},
        }

    @api.model
    def _om_dimensions(self):
        """How a row can be grouped: label, model of the ids, icon."""
        return {
            'product': {'label': self.env._("Product"), 'model': 'product.product', 'icon': 'package_2'},
            'category': {'label': self.env._("Category"), 'model': 'product.category', 'icon': 'sell'},
            'warehouse': {'label': self.env._("Warehouse"), 'model': 'stock.warehouse', 'icon': 'storefront'},
            'location': {'label': self.env._("Location"), 'model': 'stock.location', 'icon': 'location_on'},
            'lot': {'label': self.env._("Lot/Serial"), 'model': 'stock.lot', 'icon': 'barcode'},
            'package': {'label': self.env._("Package"), 'model': 'stock.package', 'icon': 'inventory_2'},
            'owner': {'label': self.env._("Owner"), 'model': 'res.partner', 'icon': 'person'},
            'partner': {'label': self.env._("Partner"), 'model': 'res.partner', 'icon': 'person'},
            'picking_type': {'label': self.env._("Operation Type"), 'model': 'stock.picking.type',
                             'icon': 'local_shipping'},
        }

    @api.model
    def _om_get_columns(self, options):
        """[{key, label, type, aggregate, visible, optional, detail_only, help}]

        type: char, date, datetime, float (quantity), monetary, int, percent.
        aggregate 'sum' sums the column on groups; other columns are set by
        _om_finalize_node. A column with optional=False is always shown.
        """
        return []

    @api.model
    def _om_columns(self, options):
        columns = self._om_get_columns(options)
        chosen = options.get('columns')
        for column in columns:
            column.setdefault('aggregate', False)
            column.setdefault('optional', True)
            column.setdefault('visible', True)
            column.setdefault('sortable', column['type'] != 'char' or not column.get('detail_only'))
            column['bar'] = column['key'] == self._report_bar_column
            if chosen and column['optional']:
                column['visible'] = column['key'] in chosen
        if options.get('compare'):
            compared = []
            for column in columns:
                compared.append(column)
                if column['key'] in self._report_compare_keys:
                    compared += self._om_compare_columns(column, options)
            columns = compared
            for column in columns:
                if chosen and column['optional'] and column.get('compare_of'):
                    base = column['compare_of']
                    column['visible'] = column['key'] in chosen or not any(
                        base + suffix in chosen for suffix in ('_cmp', '_delta', '_pct'))
        if chosen:
            order = {key: index for index, key in enumerate(chosen)}
            columns.sort(key=lambda c: order.get(c['key'], len(order)))
        return columns

    @api.model
    def _om_compare_columns(self, column, options):
        previous = self.env._("Previous") if options['compare'] == 'previous_period' else self.env._("Last Year")
        base = {'compare_of': column['key'], 'optional': True, 'visible': True}
        return [
            {**base, 'key': column['key'] + '_cmp', 'label': '%s (%s)' % (column['label'], previous),
             'type': column['type'], 'aggregate': 'sum', 'help': self._om_compare_label(options)},
            {**base, 'key': column['key'] + '_delta', 'label': '\u0394 %s' % column['label'], 'type': column['type'],
             'aggregate': 'sum'},
            {**base, 'key': column['key'] + '_pct', 'label': '\u0394 %', 'type': 'percent'},
        ]

    # ------------------------------------------------------------------
    # Common SQL helpers
    # ------------------------------------------------------------------

    @api.model
    def _om_location_ids(self, options):
        """The internal locations the report covers."""
        domain = [('usage', '=', 'internal'), ('company_id', 'in', self.env.companies.ids)]
        if options.get('location_ids'):
            domain.append(('id', 'child_of' if options['child_locations'] else 'in', options['location_ids']))
        if options.get('warehouse_ids'):
            domain.append(('warehouse_id', 'in', options['warehouse_ids']))
        return self.env['stock.location'].with_context(active_test=False).search(domain).ids

    @api.model
    def _om_product_ids(self, options):
        """Product ids chosen by the product and category filters, or None for all."""
        if not options.get('product_ids') and not options.get('category_ids'):
            return None
        domain = [('is_storable', '=', True)]
        if options.get('product_ids'):
            domain.append(('id', 'in', options['product_ids']))
        if options.get('category_ids'):
            domain.append(('categ_id', 'child_of', options['category_ids']))
        return self.env['product.product'].with_context(active_test=False).search(domain).ids

    @api.model
    def _om_digits(self):
        return self.env['decimal.precision'].precision_get('Product Unit')

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------

    @api.model
    def _om_row_dimensions(self, options):
        """The dimensions the rows must carry: the grouping, and what it derives from."""
        dims = set(options['group_by']) | {'product'}
        if 'warehouse' in dims:
            dims.add('location')
        return dims

    @api.model
    def _om_get_rows(self, options):
        """The rows of the report: dicts with '<dim>_id' keys and the measures."""
        return []

    @api.model
    def _om_enrich_rows(self, rows, options):
        """Derive category from product and warehouse from location."""
        product_ids = {r['product_id'] for r in rows if r.get('product_id')}
        if product_ids and any('category_id' not in r for r in rows):
            products = self.env['product.product'].with_context(active_test=False).browse(product_ids)
            categ_by_product = {p.id: p.categ_id.id for p in products}
            uom_by_product = {p.id: p.uom_id.display_name for p in products}
            for row in rows:
                if row.get('product_id'):
                    row.setdefault('category_id', categ_by_product.get(row['product_id']))
                    row.setdefault('uom', uom_by_product.get(row['product_id']))
        location_ids = {r['location_id'] for r in rows if r.get('location_id')}
        if location_ids and any('warehouse_id' not in r for r in rows):
            locations = self.env['stock.location'].with_context(active_test=False).browse(location_ids)
            warehouse_by_location = {loc.id: loc.warehouse_id.id for loc in locations}
            for row in rows:
                if row.get('location_id'):
                    row.setdefault('warehouse_id', warehouse_by_location.get(row['location_id']))
        return rows

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options['hide_zero']:
            keys = [c['key'] for c in columns if c.get('aggregate') == 'sum' and c['type'] in ('float', 'monetary')]
            precision = 10 ** -max(self._om_digits(), 2)
            rows = [r for r in rows if any(abs(r.get(k) or 0.0) >= precision for k in keys)]
        if options['kpi_filter']:
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        return rows

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    @api.model
    def _om_names(self, dim, ids):
        if not ids:
            return {}
        dimension = self._om_dimensions()[dim]
        if 'selection' in dimension:
            return {key: label for key, label in dimension['selection'].items() if key in ids}
        records = self.env[dimension['model']].with_context(active_test=False).browse(ids).exists()
        if dim == 'location':
            return {r.id: r.complete_name for r in records}
        return {r.id: r.display_name for r in records}

    @api.model
    def _om_empty_name(self, dim):
        return {
            'lot': self.env._("No lot/serial"),
            'package': self.env._("No package"),
            'owner': self.env._("Company stock"),
            'warehouse': self.env._("No warehouse"),
            'partner': self.env._("No partner"),
            'category': self.env._("No category"),
        }.get(dim, self.env._("None"))

    @api.model
    def _om_build_tree(self, rows, options, columns):
        """Nested nodes: {'id', 'dim', 'res_id', 'name', 'rows', 'values', 'children'}."""
        group_by = options['group_by']
        names = {dim: self._om_names(dim, list({r.get(dim + '_id') for r in rows if r.get(dim + '_id')}))
                 for dim in group_by}
        sum_keys = [c['key'] for c in columns if c.get('aggregate') == 'sum']

        def make(level_rows, level, parent_id):
            if level == len(group_by):
                return []
            dim = group_by[level]
            buckets = defaultdict(list)
            for row in level_rows:
                buckets[row.get(dim + '_id') or False].append(row)
            nodes = []
            for res_id, bucket in buckets.items():
                node_id = '%s-%s' % (dim, res_id or 0)
                if parent_id:
                    node_id = '%s|%s' % (parent_id, node_id)
                node = {
                    'id': node_id,
                    'parent_id': parent_id,
                    'level': level,
                    'dim': dim,
                    'res_id': res_id,
                    'name': names[dim].get(res_id) if res_id else self._om_empty_name(dim),
                    'rows': [r for r in bucket if not r.get('_cmp')],
                    'values': {k: sum(r.get(k) or 0.0 for r in bucket) for k in sum_keys},
                    'leaf': level == len(group_by) - 1,
                }
                node['children'] = make(bucket, level + 1, node_id)
                self._om_finalize_node(node, options)
                self._om_compare_node(node, options)
                nodes.append(node)
            return nodes

        tree = make(rows, 0, False)
        total = {
            'id': 'total', 'parent_id': False, 'level': 0, 'dim': False, 'res_id': False,
            'name': self.env._("Total"), 'rows': [r for r in rows if not r.get('_cmp')], 'leaf': False,
            'children': [], 'values': {k: sum(r.get(k) or 0.0 for r in rows) for k in sum_keys},
        }
        self._om_finalize_node(total, options)
        self._om_compare_node(total, options)
        return tree, total

    @api.model
    def _om_finalize_node(self, node, options):
        """Set the values of a group that are not sums (unit cost, ratios, UoM...)."""
        if node.get('dim') == 'product' or (node['rows'] and len({r.get('product_id') for r in node['rows']}) == 1):
            node['values']['uom'] = node['rows'][0].get('uom') if node['rows'] else ''

    @api.model
    def _om_compare_node(self, node, options):
        """Change and change in % of the compared columns."""
        if not options.get('compare'):
            return
        values = node['values']
        for key in self._report_compare_keys:
            current, previous = values.get(key) or 0.0, values.get(key + '_cmp') or 0.0
            values[key + '_delta'] = current - previous
            values[key + '_pct'] = (current - previous) / abs(previous) * 100 if previous else False

    @api.model
    def _om_sort_nodes(self, nodes, options):
        sort = options.get('sort') or {}
        key = sort.get('key')
        reverse = sort.get('dir') == 'desc'
        if key and key != 'name':
            def value_key(node):
                value = node['values'].get(key)
                if value is None or value is False:
                    return (0, 0)
                if isinstance(value, datetime):
                    return (1, value.timestamp())
                if isinstance(value, date):
                    return (1, value.toordinal())
                if isinstance(value, (int, float)):
                    return (1, value)
                return (2, str(value).casefold())

            nodes.sort(key=value_key, reverse=reverse)
        else:
            dimensions = self._om_dimensions()

            def name_key(node):
                selection = dimensions.get(node['dim'], {}).get('selection')
                if selection and node['res_id'] in selection:
                    return (False, '%03d' % list(selection).index(node['res_id']))
                return (node['res_id'] is False, (node['name'] or '').casefold())

            nodes.sort(key=name_key, reverse=reverse)
        for node in nodes:
            self._om_sort_nodes(node['children'], options)

    @api.model
    def _om_search_tree(self, nodes, search):
        """Keep the nodes whose name, or a descendant's, contains ``search``."""
        needle = search.casefold()
        kept = []
        for node in nodes:
            if needle in (node['name'] or '').casefold():
                kept.append(node)
                continue
            node['children'] = self._om_search_tree(node['children'], search)
            if node['children']:
                kept.append(node)
        return kept

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    @api.model
    def _om_node_line(self, node, options):
        has_children = bool(node['children']) or (node['leaf'] and self._om_has_details(options))
        line = {
            'id': node['id'],
            'parent_id': node['parent_id'],
            'level': node['level'],
            'kind': 'leaf' if node['leaf'] else 'group',
            'dim': node['dim'],
            'name': node['name'],
            'values': node['values'],
            'has_children': has_children,
            'count': len(node['children']),
            'open': self._om_node_open(node, options),
            'links': self._om_node_links(node, options),
        }
        return line

    @api.model
    def _om_node_filters(self, node):
        """The options that restrict a report to the node: its dimensions and those above it."""
        filters = {}
        for part in node['id'].split('|'):
            dim, _sep, res_id = part.rpartition('-')
            if not res_id.isdigit():
                continue
            res_id = int(res_id)
            option = {'product': 'product_ids', 'category': 'category_ids', 'warehouse': 'warehouse_ids',
                      'location': 'location_ids', 'lot': 'lot_ids', 'owner': 'owner_ids',
                      'partner': 'partner_ids', 'picking_type': 'picking_type_ids'}.get(dim)
            if option and res_id:
                filters[option] = [res_id]
        return filters

    @api.model
    def _om_node_open(self, node, options):
        dim = node.get('dim')
        if not dim or not node.get('res_id'):
            return False
        model = self._om_dimensions()[dim].get('model')
        if not model:
            return False
        return {'res_model': model, 'res_id': node['res_id']}

    @api.model
    def _om_node_links(self, node, options):
        """Other reports the node can be opened in, filtered on it."""
        if 'product_ids' not in self._om_node_filters(node):
            return []
        links = []
        filters = self._om_node_filters(node)
        for key, label in self._om_link_targets():
            if key == self._report_key:
                continue
            try:
                target = self._om_report(key)
            except UserError:
                continue
            link_options = {**filters, 'date_preset': options['date_preset'],
                            'date_from': options['date_from'], 'date_to': options['date_to']}
            if 'location_ids' in filters:
                link_options['child_locations'] = False
            links.append({'report': key, 'label': label, 'icon': target._report_icon, 'options': link_options})
        return links

    @api.model
    def _om_link_targets(self):
        return [
            ('stock_card', self.env._("Open Stock Card")),
            ('stock_on_hand', self.env._("Open Stock on Hand")),
            ('ageing', self.env._("Open Stock Ageing")),
        ]

    @api.model
    def _om_find_node(self, nodes, line_id):
        for node in nodes:
            if node['id'] == line_id:
                return node
            if line_id.startswith(node['id'] + '|'):
                return self._om_find_node(node['children'], line_id)
        return None

    @api.model
    def _om_cache_key(self, options):
        return (self.env.cr.dbname, self._name, self.env.uid, tuple(self.env.companies.ids), self.env.lang,
                self.env.context.get('tz'), json.dumps(options, sort_keys=True, default=str))

    @api.model
    def _om_compute_cached(self, options, fresh=False):
        """The computed report: fresh when the report is opened or its options
        change, from the cache when the same report is unfolded or exported."""
        key = self._om_cache_key(options)
        now = clock.monotonic()
        if not fresh:
            with _cache_lock:
                hit = _cache.get(key)
                if hit and now - hit[0] < CACHE_SECONDS:
                    _cache.move_to_end(key)
                    return hit[1]
        data = self._om_compute(options)
        with _cache_lock:
            _cache[key] = (now, data)
            _cache.move_to_end(key)
            while len(_cache) > CACHE_SIZE:
                _cache.popitem(last=False)
        return data

    @api.model
    def _om_compute(self, options):
        columns = self._om_columns(options)
        rows = self._om_enrich_rows(self._om_get_rows(options), options)
        all_rows = rows
        rows = self._om_filter_rows(rows, options, columns)
        compare_rows = self._om_compare_rows(options, columns, rows) if options.get('compare') else []
        tree, total = self._om_build_tree(rows + compare_rows, options, columns)
        if options['search']:
            tree = self._om_search_tree(tree, options['search'])
        self._om_sort_nodes(tree, options)
        return {'columns': columns, 'tree': tree, 'total': total, 'rows': rows, 'all_rows': all_rows}

    @api.model
    def _om_compare_rows(self, options, columns, rows):
        """The rows of the earlier period, carrying only '<key>_cmp' sums, so that
        they fall in the same groups as the current rows and add up with them."""
        compare_options = self._om_compare_options(options)
        sum_keys = [c['key'] for c in self._om_columns(compare_options)
                    if c.get('aggregate') == 'sum' and c['type'] not in ('char', 'date', 'datetime')]
        previous = self._om_enrich_rows(self._om_get_rows(compare_options), compare_options)
        precision = 10 ** -max(self._om_digits(), 2)
        result = []
        for row in previous:
            new = {k: v for k, v in row.items() if k.endswith('_id') or k == 'uom'}
            new.update({key + '_cmp': row.get(key) or 0.0 for key in sum_keys})
            new['_cmp'] = True
            if options['hide_zero'] and not any(abs(new[k + '_cmp']) >= precision for k in sum_keys):
                continue
            result.append(new)
        if options['kpi_filter'] or options['search']:
            # only for what the current rows show
            dims = [d + '_id' for d in self._om_row_dimensions(options)]
            shown = {tuple(r.get(d) for d in dims) for r in rows}
            result = [r for r in result if tuple(r.get(d) for d in dims) in shown]
        return result

    @api.model
    def _om_children_lines(self, data, options, parent, offset=0, limit=PAGE_SIZE):
        """The lines under ``parent`` (a node, or None for the top), and how many are left."""
        if parent is None:
            nodes = data['tree']
        elif parent['children']:
            nodes = parent['children']
        elif parent['leaf'] and self._om_has_details(options):
            details = self._om_detail_lines(parent, options)
            page = details[offset:offset + limit] if limit else details[offset:]
            return page, max(len(details) - offset - len(page), 0)
        else:
            return [], 0
        page = nodes[offset:offset + limit] if limit else nodes[offset:]
        return [self._om_node_line(n, options) for n in page], max(len(nodes) - offset - len(page), 0)

    @api.model
    def _om_has_details(self, options):
        return self._report_has_details

    @api.model
    def _om_detail_lines(self, node, options):
        """Detail lines of a leaf (moves, quants...), each with 'id', 'kind': 'detail', 'values'."""
        return []

    @api.model
    def _om_detail_line(self, node, index, name, values, open_action=False, kind='detail'):
        return {
            'id': '%s|d-%s' % (node['id'], index),
            'parent_id': node['id'],
            'level': node['level'] + 1,
            'kind': kind,
            'dim': False,
            'name': name,
            'values': values,
            'has_children': False,
            'count': 0,
            'open': open_action,
            'links': [],
        }

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    @api.model
    def _om_get_kpis(self, data, options):
        """[{key, label, value, type, icon, tone, filter}]; filter is a kpi_filter key or False."""
        return []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def om_get_report(self, options=None, expanded=None):
        """Everything the screen needs to draw the report.

        ``expanded``: ids of the unfolded lines; their children come too, so the
        report reopens the way it was left.
        """
        self._om_check_access()
        options = self._om_normalize_options(options)
        data = self._om_compute_cached(options, fresh=True)
        lines, more = self._om_children_lines(data, options, None)
        children = {}
        for line_id in expanded or []:
            node = self._om_find_node(data['tree'], line_id)
            if node:
                child_lines, child_more = self._om_children_lines(data, options, node)
                children[line_id] = {'lines': child_lines, 'more': child_more}
        return {
            'key': self._report_key,
            'name': self._om_report_title(),
            'model': self._name,
            'icon': self._report_icon,
            'description': str(self._report_description or ''),
            'options': options,
            'date_mode': self._report_date_mode,
            'filters': self._om_filters_meta(),
            'group_by': self._om_group_by_meta(),
            'columns': data['columns'],
            'lines': lines,
            'more': more,
            'children': children,
            'total': self._om_total_line(data, options),
            'kpis': self._om_compare_kpis(self._om_get_kpis(data, options), data, options),
            'toggles': self._om_toggles(options),
            'compare_available': bool(self._report_compare_keys) and self._report_date_mode != 'none',
            'compare_label': self._om_compare_label(options),
            'extra_options': self._om_extra_options_meta(options),
            'currency_id': self.env.company.currency_id.id,
            'digits': self._om_digits(),
            'subtitle': self._om_subtitle(options),
        }

    @api.model
    def om_get_children(self, options, line_id, offset=0):
        self._om_check_access()
        options = self._om_normalize_options(options)
        data = self._om_compute_cached(options)
        node = self._om_find_node(data['tree'], line_id) if line_id else None
        if line_id and not node:
            return {'lines': [], 'more': 0}
        lines, more = self._om_children_lines(data, options, node, offset=offset)
        return {'lines': lines, 'more': more}

    @api.model
    def _om_compare_kpis(self, kpis, data, options):
        """The previous value of the key figures that are compared columns."""
        if not options.get('compare'):
            return kpis
        total = data['total']['values']
        for kpi in kpis:
            key = kpi.get('compare_key', kpi['key'])
            if key in self._report_compare_keys:
                kpi['previous'] = total.get(key + '_cmp') or 0.0
                kpi['delta_pct'] = total.get(key + '_pct')
        return kpis

    @api.model
    def _om_total_line(self, data, options):
        total = data['total']
        return {'id': 'total', 'kind': 'total', 'level': 0, 'name': total['name'], 'values': total['values']}

    @api.model
    def _om_filters_meta(self):
        definitions = self._om_filter_definitions()
        return [{'key': key, **definitions[key]} for key in self._report_filters if key in definitions]

    @api.model
    def _om_group_by_meta(self):
        dimensions = self._om_dimensions()
        return [{'key': key, 'label': dimensions[key]['label'], 'icon': dimensions[key]['icon']}
                for key in self._report_group_by]

    @api.model
    def _om_toggles(self, options):
        """The on/off options of the options menu: [{key, label, help}]."""
        toggles = [{'key': 'hide_zero', 'label': self.env._("Hide zero lines")}]
        if 'location' in self._report_filters:
            toggles.append({'key': 'child_locations', 'label': self.env._("Include sub-locations")})
        return toggles

    @api.model
    def _om_extra_options_meta(self, options):
        """Numeric options of the report: [{key, label, min, max, step}]."""
        return []

    @api.model
    def _om_subtitle(self, options):
        """One line saying what the report shows, for the screen, the PDF and the Excel file."""
        if self._report_date_mode == 'none':
            return ''
        lang = self.env['res.lang']._get_data(code=self.env.lang or 'en_US')
        fmt = lang.date_format if lang else '%m/%d/%Y'
        date_to = fields.Date.to_date(options['date_to'])
        if self._report_date_mode == 'as_of':
            return self.env._("As of %s", date_to.strftime(fmt))
        date_from = fields.Date.to_date(options['date_from'])
        return self.env._("From %(start)s to %(end)s", start=date_from.strftime(fmt), end=date_to.strftime(fmt))

    @api.model
    def _om_filter_summary(self, options):
        """[(label, value)] of the active filters, printed above the exported table."""
        summary = []
        subtitle = self._om_subtitle(options)
        if subtitle:
            summary.append((self.env._("Period"), subtitle))
        for meta in self._om_filters_meta():
            ids = options.get(meta['option'])
            if ids:
                records = self.env[meta['model']].with_context(active_test=False).browse(ids).exists()
                summary.append((meta['label'], ', '.join(records.mapped('display_name'))))
        dims = {g['key']: g['label'] for g in self._om_group_by_meta()}
        summary.append((self.env._("Grouped by"), ' > '.join(dims[g] for g in options['group_by'])))
        if options['search']:
            summary.append((self.env._("Search"), options['search']))
        if options.get('compare'):
            summary.append((self.env._("Compared with"), self._om_compare_label(options)))
        return summary

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def om_export_data(self, options, expanded=None, expand_all=False):
        """Flat lines of the report as printed: the top lines, and under them
        the children of the unfolded lines (or of every line)."""
        self._om_check_access()
        options = self._om_normalize_options(options)
        data = self._om_compute_cached(options)
        expanded = set(expanded or [])
        flat = []

        def walk(parent):
            lines, _more = self._om_children_lines(data, options, parent, limit=0)
            for line in lines:
                if len(flat) >= EXPORT_LIMIT:
                    return
                flat.append(line)
                if line['has_children'] and (expand_all or line['id'] in expanded) and line['kind'] != 'detail':
                    node = self._om_find_node(data['tree'], line['id'])
                    if node:
                        walk(node)

        walk(None)
        return {
            'title': self._om_report_title(),
            'subtitle': self._om_subtitle(options),
            'filters': self._om_filter_summary(options),
            'columns': [c for c in data['columns'] if c['visible']],
            'lines': flat,
            'total': self._om_total_line(data, options),
            'kpis': self._om_compare_kpis(self._om_get_kpis(data, options), data, options),
            'group_label': ' / '.join(
                {g['key']: g['label'] for g in self._om_group_by_meta()}[g] for g in options['group_by']),
            'currency': self.env.company.currency_id,
            'company': self.env.company,
            'digits': self._om_digits(),
            'options': options,
        }
