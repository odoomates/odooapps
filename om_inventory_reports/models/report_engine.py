from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odoo import api, fields, models
from odoo.exceptions import UserError

# the options of the records a report can be narrowed down to, by filter
FILTER_OPTIONS = {
    'warehouse': 'warehouse_ids',
    'location': 'location_ids',
    'product': 'product_ids',
    'category': 'category_ids',
    'lot': 'lot_ids',
    'owner': 'owner_ids',
    'partner': 'partner_ids',
    'picking_type': 'picking_type_ids',
}
# the toggles every report has, on by default
TOGGLE_DEFAULTS = {'hide_zero': True, 'child_locations': True}


class OmInventoryReport(models.AbstractModel):
    """The inventory reports, on the report engine (om.report).

    Every report is an abstract model inheriting this one. A report says what it
    is (the ``_report_*`` attributes), which columns it has, and gives its rows:
    plain dicts with the ids of the dimensions (product, location, ...) and the
    measures. The engine filters the rows, builds the groups the user asked for,
    sums the measures, sorts, pages, and serves the same lines to the screen,
    the PDF and the Excel file, so the three always agree. This model adds what
    the inventory reports share: their filters, the time zone of the moves, the
    product and location helpers, and the units of measure.
    """
    _name = 'om.inventory.report'
    _inherit = 'om.report'
    _description = 'Inventory Report'

    _report_app = 'stock'
    _report_group = 'stock.group_stock_user'
    # the key of a report: how the other reports link to it
    _report_key = None
    _report_section = 'stock'
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('category', 'product', 'warehouse', 'location')
    _report_default_group_by = ('category', 'product')
    # options of the report beyond the common ones, with their default
    _report_extra_options = {}

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    @api.model
    def _om_report(self, key):
        """The inventory report ``key``."""
        for report in self._om_report_models(self._report_app):
            if getattr(report, '_report_key', None) == key:
                return report
        raise UserError(self.env._("This report does not exist: %s", key))

    @api.model
    def _om_sections(self):
        return {
            'stock': self.env._("Stock"),
            'movement': self.env._("Movements"),
            'valuation': self.env._("Valuation"),
            'analysis': self.env._("Analysis"),
            'operations': self.env._("Operations"),
        }

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    @api.model
    def _om_filter_definitions(self):
        companies = self.env.companies.ids
        # the labels apart: a tuple right after a translated string would be extracted as a term too
        labels = {
            'warehouse': self.env._("Warehouse"),
            'location': self.env._("Location"),
            'product': self.env._("Product"),
            'category': self.env._("Category"),
            'lot': self.env._("Lot/Serial"),
            'owner': self.env._("Owner"),
            'partner': self.env._("Partner"),
            'picking_type': self.env._("Operation Type"),
        }
        return {
            'warehouse': {'label': labels['warehouse'], 'model': 'stock.warehouse', 'icon': 'storefront',
                          'domain': [('company_id', 'in', companies)]},
            'location': {'label': labels['location'], 'model': 'stock.location', 'icon': 'location_on',
                         'domain': [('usage', 'in', ('internal', 'view')), ('company_id', 'in', companies + [False])]},
            'product': {'label': labels['product'], 'model': 'product.product', 'icon': 'package_2',
                        'domain': [('is_storable', '=', True)]},
            'category': {'label': labels['category'], 'model': 'product.category', 'icon': 'sell', 'domain': []},
            'lot': {'label': labels['lot'], 'model': 'stock.lot', 'icon': 'barcode',
                    'domain': [('company_id', 'in', companies + [False])]},
            'owner': {'label': labels['owner'], 'model': 'res.partner', 'icon': 'person', 'domain': []},
            'partner': {'label': labels['partner'], 'model': 'res.partner', 'icon': 'person', 'domain': []},
            'picking_type': {'label': labels['picking_type'], 'model': 'stock.picking.type',
                             'icon': 'local_shipping', 'domain': [('company_id', 'in', companies)]},
        }

    @api.model
    def _om_filters(self):
        definitions = self._om_filter_definitions()
        return [{'key': FILTER_OPTIONS[key], **definitions[key]}
                for key in self._report_filters if key in definitions]

    @api.model
    def _om_toggles(self):
        """The on/off options of the options menu; a report adds its own (with their default in
        _report_extra_options)."""
        toggles = [{'key': 'hide_zero', 'label': self.env._("Hide zero lines"), 'default': True}]
        if 'location' in self._report_filters:
            toggles.append({'key': 'child_locations', 'label': self.env._("Include sub-locations"),
                            'default': True})
        return toggles

    @api.model
    def _om_extra_options_meta(self, options):
        """Numeric options of the report: [{key, label, min, max, step}], their default in
        _report_extra_options."""
        return []

    @api.model
    def _om_numbers(self):
        numbers = []
        for spec in self._om_extra_options_meta({}):
            default = self._report_extra_options.get(spec['key'], spec.get('default', 0))
            if spec.get('step', 1) != int(spec.get('step', 1)):
                # a threshold in halves (a turnover of 2.5) stays a decimal number
                default = float(default)
            numbers.append({**spec, 'default': default})
        return numbers

    @api.model
    def _om_default_options(self):
        options = super()._om_default_options()
        if not self._report_default_preset and self._report_date_mode != 'none':
            options['date_preset'] = 'this_month' if self._report_date_mode == 'range' else 'today'
        # every record filter, even those the report does not show: another report links with them
        for option in FILTER_OPTIONS.values():
            options.setdefault(option, [])
        # the zero lines are hidden and the sub-locations included, also in a report without these toggles
        options.setdefault('hide_zero', True)
        options.setdefault('child_locations', True)
        for spec in self._om_toggles():
            if spec['key'] in self._report_extra_options:
                options[spec['key']] = bool(self._report_extra_options[spec['key']])
            elif 'default' not in spec:
                options[spec['key']] = TOGGLE_DEFAULTS.get(spec['key'], False)
        for key, value in self._report_extra_options.items():
            options.setdefault(key, value)
        return options

    @api.model
    def _om_normalize_options(self, options):
        options = super()._om_normalize_options(options)
        for option in FILTER_OPTIONS.values():
            options[option] = [int(i) for i in options.get(option) or [] if str(i).isdigit()]
        return options

    @api.model
    def _om_date_presets(self):
        return [
            {'key': 'today', 'label': self.env._("Today")},
            {'key': 'yesterday', 'label': self.env._("Yesterday")},
            {'key': 'this_week', 'label': self.env._("This week")},
            {'key': 'this_month', 'label': self.env._("This month")},
            {'key': 'this_quarter', 'label': self.env._("This quarter")},
            {'key': 'this_year', 'label': self.env._("This year")},
            {'key': 'last_week', 'label': self.env._("Last week"), 'separator': True},
            {'key': 'last_month', 'label': self.env._("Last month")},
            {'key': 'last_quarter', 'label': self.env._("Last quarter")},
            {'key': 'last_year', 'label': self.env._("Last year")},
        ]

    @api.model
    def _om_preset_dates(self, preset, today):
        if preset == 'yesterday':
            day = today - timedelta(days=1)
            return day, day
        if preset in ('this_week', 'last_week'):
            start = today - timedelta(days=today.weekday())
            if preset == 'last_week':
                start -= timedelta(days=7)
            return start, start + timedelta(days=6)
        if preset in ('this_year', 'last_year'):
            start = date(today.year - (preset == 'last_year'), 1, 1)
            return start, date(start.year, 12, 31)
        return super()._om_preset_dates(preset, today)

    @api.model
    def _om_compare_options(self, options):
        """The options of the nearest period compared with."""
        periods = self._om_compare_periods(options)
        if not periods:
            return options
        return {**options, 'date_preset': 'custom', 'compare': False, 'kpi_filter': False, 'search': '',
                'date_from': periods[0]['date_from'], 'date_to': periods[0]['date_to']}

    @api.model
    def _om_datetime_end(self, day):
        """The last instant of ``day`` in the user's time zone, as a naive UTC datetime."""
        return self._om_datetime_start(fields.Date.to_date(day) + timedelta(days=1))

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
    # Dimensions, columns
    # ------------------------------------------------------------------

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
    def _om_columns(self, options):
        columns = super()._om_columns(options)
        digits = self._om_digits()
        for column in columns:
            if column['type'] == 'float':
                column.setdefault('digits', digits)
            elif column['type'] == 'days':
                column.setdefault('digits', 0)
            # a detail line (a move, a quant) leaves its zeros blank, but its running balance
            if column['type'] in ('float', 'monetary', 'int', 'percent', 'days', 'ratio') \
                    and column['key'] != 'balance':
                column['blank_zero'] = True
        return columns

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
    def _om_product_costs(self, product_ids, options):
        """{product id: unit cost} for stock values. The product's cost here; the
        valuation module puts Odoo's own valuation at the period's end in its place."""
        products = self.env['product.product'].with_context(active_test=False).browse(set(product_ids))
        return {p.id: p.standard_price for p in products}

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
    def _om_zero_precision(self):
        return 10 ** -max(self._om_digits(), 2)

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options.get('hide_zero'):
            keys = [c['key'] for c in columns if c.get('aggregate') == 'sum' and c['type'] in ('float', 'monetary')]
            precision = self._om_zero_precision()
            rows = [r for r in rows if any(abs(r.get(k) or 0.0) >= precision for k in keys)]
        if options.get('kpi_filter'):
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_compare_match_keys(self, options):
        return sorted(dim + '_id' for dim in self._om_row_dimensions(options))

    @api.model
    def _om_compare_carried(self):
        return ('uom',)

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    @api.model
    def _om_names(self, dim, ids):
        if dim == 'location' and ids:
            records = self.env['stock.location'].with_context(active_test=False).browse(ids).exists()
            return {r.id: r.complete_name for r in records}
        return super()._om_names(dim, ids)

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
    def _om_finalize_node(self, node, options):
        """Set the values of a group that are not sums (unit cost, ratios, UoM...)."""
        if node.get('dim') == 'product' or (node['rows'] and len({r.get('product_id') for r in node['rows']}) == 1):
            node['values']['uom'] = node['rows'][0].get('uom') if node['rows'] else ''

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    @api.model
    def _om_node_filters(self, node):
        """The options that restrict a report to the node: its dimensions and those above it."""
        filters = {}
        for part in node['id'].split('|'):
            dim, _sep, res_id = part.rpartition('-')
            if not res_id.isdigit():
                continue
            res_id = int(res_id)
            option = FILTER_OPTIONS.get(dim)
            if option and res_id:
                filters[option] = [res_id]
        return filters

    @api.model
    def _om_node_links(self, node, options):
        """Other reports the node can be opened in, filtered on it."""
        filters = self._om_node_filters(node)
        if 'product_ids' not in filters:
            return []
        links = []
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
            links.append(self._om_link(target._name, label, link_options))
        return links

    @api.model
    def _om_link_targets(self):
        """ :return: [(report key, button label)] """
        labels = {
            'stock_card': self.env._("Open Stock Card"),
            'stock_on_hand': self.env._("Open Stock on Hand"),
            'ageing': self.env._("Open Stock Ageing"),
        }
        return list(labels.items())

    @api.model
    def _om_detail_line(self, node, index, name, values, open_action=False, kind='detail'):
        line = self._om_line('%s|d-%s' % (node['id'], index), name, values, parent_id=node['id'],
                             level=node['level'] + 1, kind=kind, dim=False)
        line['open'] = open_action
        return line
