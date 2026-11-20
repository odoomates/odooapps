import json
import threading
import time as clock
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

# lines sent per request; the screen asks for the next page with "Show more"
PAGE_SIZE = 200
# lines written to a PDF, Excel or CSV file at most
EXPORT_LIMIT = 100000

# A computed report is kept a short while, by user, companies and options, so
# that unfolding a line or showing more lines does not compute it again
CACHE_SIZE = 16
CACHE_SECONDS = 120
_cache = OrderedDict()
_cache_lock = threading.Lock()

COLUMN_TYPES = ('char', 'date', 'datetime', 'monetary', 'float', 'int', 'percent', 'ratio', 'days')
NUMERIC_TYPES = ('monetary', 'float', 'int', 'percent', 'ratio', 'days')

# how the amounts are shown: (key, factor, suffix); 'decimals' as the currency rounds them
ROUNDING_UNITS = (
    ('decimals', 1, ''),
    ('units', 1, ''),
    ('thousands', 1000, 'K'),
    ('millions', 1000000, 'M'),
)
LINE_KINDS = ('group', 'leaf', 'detail', 'opening', 'closing', 'section', 'total')
# the catalog entry of the overview of an app
OVERVIEW = 'overview'


class OmReport(models.AbstractModel):
    """The engine of the dynamic reports.

    A report is an abstract model inheriting this one. It is written in Python
    only: the screen (filters, table, folding, saved views, PDF, Excel and CSV)
    comes with the engine and draws whatever the report declares.

    The smallest report says what it is, which columns it has and gives its
    rows; the engine groups them, sums the columns, sorts, searches and pages::

        class ReportSalesByCustomer(models.AbstractModel):
            _name = 'om.report.sales.customer'
            _inherit = 'om.report'
            _description = 'Sales by Customer'
            _report_name = 'Sales by Customer'
            _report_group_by = ('partner', 'product')

            def _om_dimensions(self):
                return {'partner': {'label': self.env._("Customer"), 'model': 'res.partner'},
                        'product': {'label': self.env._("Product"), 'model': 'product.product'}}

            def _om_get_columns(self, options):
                return [{'key': 'amount', 'label': self.env._("Amount"), 'type': 'monetary',
                         'aggregate': 'sum'}]

            def _om_get_rows(self, options):
                return [{'partner_id': ..., 'product_id': ..., 'amount': ...}, ...]

    and an ``ir.actions.client`` with the tag ``om_report`` and the context
    ``{'om_report_model': 'om.report.sales.customer'}`` opens it.

    A report whose lines are not a grouping of rows (a ledger, a balance
    sheet) overrides ``_om_compute`` and ``_om_lines`` instead and builds its
    lines with ``_om_line``.

    A line, as the screen, the PDF and the Excel file get it::

        {'id': 'account-4|aml-12', 'parent_id': 'account-4', 'level': 1,
         'kind': 'group' | 'leaf' | 'detail' | 'opening' | 'closing' | 'section' | 'total',
         'name': 'INV/2026/0001', 'values': {column key: value}, 'has_children': False,
         'count': 0, 'open': {'res_model': 'account.move', 'res_id': 7} or False,
         'drill': True (the report gives an action for the line, see _om_line_action),
         'unfolded': True (the line opens unfolded when the report is opened),
         'actions': [{'key', 'label', 'icon'}] (buttons of the line, see _om_line_button),
         'types': {column key: type} (a figure of another type than its column: a ratio, days...),
         'links': [{'model': 'om.report...', 'label': ..., 'icon': ..., 'options': {...}}]}
    """
    _name = 'om.report'
    _description = 'Dynamic Report'

    # what a report is; a report sets at least _report_name
    _report_name = ''
    _report_description = ''
    # the reports of one app share the report switcher
    _report_app = False
    _report_section = False
    _report_sequence = 100
    _report_icon = 'table'
    # 'range' (from - to), 'as_of' (one date) or 'none'
    _report_date_mode = 'range'
    _report_default_preset = False
    # who may open the report: xml ids of groups, comma separated, any of them
    _report_group = 'base.group_user'
    # the header of the first column
    _report_name_label = ''
    _report_page_size = PAGE_SIZE
    # comparison with earlier periods (the report says how in _om_compare_*)
    _report_compare = False
    # the amounts can be shown in units, thousands or millions
    _report_rounding = False

    # grouping rows: the dimensions offered and those chosen by default
    _report_group_by = ()
    _report_default_group_by = ()
    # leaves have detail lines, loaded when unfolded (_om_detail_lines)
    _report_has_details = False
    # the groups open unfolded when the report is opened
    _report_expand_default = False
    # sums compared with earlier periods, for a report that groups rows: the engine computes the rows of
    # each period compared with and adds a column of the period, the change and the change in % to each
    _report_compare_keys = ()
    # the main column, drawn with a bar in each cell to compare the lines at a glance
    _report_bar_column = False
    # a card of the report on the overview of its app, in this order (see om_get_overview)
    _report_overview = False

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    @api.model
    def _om_report_models(self, app=False):
        """The reports the user may open, of ``app`` when given."""
        reports = []
        for name in self.env.registry.descendants(['om.report'], '_inherit'):
            if name == 'om.report':
                continue
            report = self.env[name]
            if not report._report_name or (app and report._report_app != app):
                continue
            if report._om_report_available() and report._om_has_access():
                reports.append(report)
        return sorted(reports, key=lambda r: (r._report_sequence, str(r._report_name)))

    @api.model
    def _om_get_report_model(self, name):
        """The report model ``name``, after checking it is one and may be opened."""
        if not name or name == 'om.report' or name not in self.env.registry.descendants(['om.report'], '_inherit'):
            raise UserError(self.env._("This report does not exist: %s", name))
        report = self.env[name]
        if not report._report_name or not report._om_report_available():
            raise UserError(self.env._("This report does not exist: %s", name))
        report._om_check_access()
        return report

    @api.model
    def _om_report_available(self):
        """False to hide the report, e.g. without the feature it reports on."""
        return True

    @api.model
    def _om_sections(self):
        """{section key: label} of the switcher."""
        return {}

    @api.model
    def om_get_catalog(self, app=False):
        """The reports of the switcher, by section; the overview of the app first when it has one."""
        sections = self._om_sections()
        catalog = []
        reports = self._om_report_models(app)
        if app and any(report._report_overview for report in reports):
            catalog.append({
                'model': OVERVIEW,
                'name': self.env._("Overview"),
                'description': self.env._("Key figures of every report, at a glance."),
                'icon': 'grid_view',
                'section': 'overview',
                'section_name': self.env._("Overview"),
            })
        for report in reports:
            section_names = {**sections, **report._om_sections()}
            catalog.append({
                'model': report._name,
                'name': report._om_report_title(),
                'description': str(report._report_description or ''),
                'icon': report._report_icon,
                'section': report._report_section or '',
                'section_name': section_names.get(report._report_section, report._report_section or ''),
            })
        return catalog

    def _om_report_title(self):
        return str(self._report_name)

    @api.model
    def om_get_overview(self, app):
        """A card per report of ``app`` that has ``_report_overview``, with its first key figures as
        the report opens by default."""
        reports = sorted((r for r in self._om_report_models(app) if r._report_overview),
                         key=lambda r: r._report_overview)
        cards = []
        for report in reports:
            options = report._om_normalize_options({})
            prepared = report._om_prepare(options)
            data = prepared._om_compute(options)
            cards.append({
                'model': report._name,
                'name': report._om_report_title(),
                'icon': report._report_icon,
                'description': str(report._report_description or ''),
                'subtitle': prepared._om_subtitle(options),
                'kpis': prepared._om_get_kpis(data, options)[:4],
                'currency_id': prepared._om_currency().id,
                'digits': prepared._om_digits(),
            })
        return {'cards': cards}

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @api.model
    def _om_has_access(self):
        groups = [group.strip() for group in (self._report_group or '').split(',') if group.strip()]
        return not groups or any(self.env.user.has_group(group) for group in groups)

    @api.model
    def _om_check_access(self):
        if not self._om_has_access():
            raise AccessError(self.env._("You are not allowed to open the report %s.", self._om_report_title()))

    # ------------------------------------------------------------------
    # Options: declared by the report, normalized here
    # ------------------------------------------------------------------

    @api.model
    def _om_filters(self):
        """Records the report can be narrowed down to, one dropdown each.

        [{'key': 'journal_ids', 'label': ..., 'model': 'account.journal',
          'icon': 'book', 'domain': [...]}]; the option is the list of ids.
        """
        return []

    @api.model
    def _om_toggles(self):
        """On/off options of the options menu: [{'key', 'label', 'default', 'help'}]."""
        return []

    @api.model
    def _om_choices(self):
        """One-of options of the options menu, or of a dropdown of their own
        (``'menu': 'bar'``): [{'key', 'label', 'default', 'icon', 'choices': [(value, label)]}]."""
        return []

    @api.model
    def _om_engine_choices(self):
        """The one-of options the engine adds to every report declaring them (the rounding of the amounts)."""
        if not self._report_rounding:
            return []
        return [{'key': 'rounding_unit', 'label': self.env._("Amounts"), 'default': 'decimals', 'choices': [
            ['decimals', self.env._("With decimals")],
            ['units', self.env._("In units")],
            ['thousands', self.env._("In thousands (K)")],
            ['millions', self.env._("In millions (M)")],
        ]}]

    @api.model
    def _om_all_choices(self):
        return self._om_choices() + self._om_engine_choices()

    @api.model
    def _om_rounding(self, options):
        """{'factor', 'suffix'} the amounts are divided by and followed with, False to show them as they are."""
        unit = options.get('rounding_unit') or 'decimals'
        if not self._report_rounding or unit == 'decimals':
            return False
        _key, factor, suffix = next(item for item in ROUNDING_UNITS if item[0] == unit)
        return {'factor': factor, 'suffix': suffix}

    @api.model
    def _om_numbers(self):
        """Numeric options: [{'key', 'label', 'default', 'min', 'max', 'step'}]."""
        return []

    @api.model
    def _om_default_options(self):
        options = {
            'date_preset': self._report_default_preset or self._om_date_presets()[0]['key']
            if self._report_date_mode != 'none' else False,
            'date_from': False,
            'date_to': False,
            'search': '',
            'columns': False,
            'sort': False,
            'group_by': list(self._report_default_group_by),
            'compare': False,
            'compare_periods': 1,
            'compare_date_from': False,
            'compare_date_to': False,
            # a key figure, chart bar or matrix cell the report is narrowed down to (_om_kpi_filter_rows)
            'kpi_filter': False,
        }
        for spec in self._om_filters():
            options[spec['key']] = []
        for spec in self._om_toggles():
            options[spec['key']] = bool(spec.get('default'))
        for spec in self._om_all_choices():
            options[spec['key']] = spec.get('default', spec['choices'][0][0])
        for spec in self._om_numbers():
            options[spec['key']] = spec.get('default', 0)
        return options

    @api.model
    def _om_normalize_options(self, options):
        """The options as the report understands them: unknown keys dropped,
        types forced, the dates of the period filled in."""
        defaults = self._om_default_options()
        given = options or {}
        options = {**defaults, **{k: v for k, v in given.items() if k in defaults}}
        for spec in self._om_filters():
            options[spec['key']] = [int(i) for i in options[spec['key']] or [] if str(i).isdigit()]
        for spec in self._om_toggles():
            options[spec['key']] = bool(options[spec['key']])
        for spec in self._om_all_choices():
            if options[spec['key']] not in [value for value, _label in spec['choices']]:
                options[spec['key']] = defaults[spec['key']]
        for spec in self._om_numbers():
            try:
                value = float(options[spec['key']])
            except (TypeError, ValueError):
                value = defaults[spec['key']]
            if spec.get('min') is not None:
                value = max(value, spec['min'])
            if spec.get('max') is not None:
                value = min(value, spec['max'])
            options[spec['key']] = int(value) if isinstance(defaults[spec['key']], int) else value
        if self._report_group_by:
            group_by = [g for g in options['group_by'] or [] if g in self._report_group_by]
            options['group_by'] = list(dict.fromkeys(group_by))[:3] or list(self._report_default_group_by)
        else:
            options['group_by'] = []
        if self._report_date_mode == 'none':
            options.update(date_preset=False, date_from=False, date_to=False)
        else:
            if options['date_preset'] not in [p['key'] for p in self._om_date_presets()] + ['custom']:
                options['date_preset'] = defaults['date_preset']
            date_from, date_to = self._om_period(options)
            options['date_from'] = date_from and fields.Date.to_string(date_from)
            options['date_to'] = date_to and fields.Date.to_string(date_to)
        options['search'] = (options['search'] or '').strip()
        if options['columns'] and not isinstance(options['columns'], (list, dict)):
            options['columns'] = False
        if not isinstance(options['sort'], dict) or not options['sort'].get('key'):
            options['sort'] = False
        if not self._om_compares() or options['compare'] not in [c['key'] for c in self._om_all_compare_choices()]:
            options['compare'] = False
        if not isinstance(options['kpi_filter'], str) or not options['kpi_filter']:
            options['kpi_filter'] = False
        for key in ('compare_date_from', 'compare_date_to'):
            try:
                options[key] = options[key] and fields.Date.to_string(fields.Date.to_date(options[key]))
            except (TypeError, ValueError):
                options[key] = False
        if self._report_date_mode == 'as_of':
            options['compare_date_from'] = False
        try:
            options['compare_periods'] = min(max(int(options['compare_periods'] or 1), 1), 12)
        except (TypeError, ValueError):
            options['compare_periods'] = 1
        return self._om_clean_options(options)

    @api.model
    def _om_clean_options(self, options):
        """Last word of the report on its options (an option that rules out another...)."""
        return options

    @api.model
    def _om_prepare(self, options):
        """The report to compute ``options`` with: itself by default, or with a context of its own
        (a date to convert currencies at...)."""
        return self

    # ------------------------------------------------------------------
    # Periods
    # ------------------------------------------------------------------

    @api.model
    def _om_date_presets(self):
        """The periods of the date dropdown: [{'key', 'label', 'separator'}]."""
        if self._report_date_mode == 'as_of':
            return [
                {'key': 'today', 'label': self.env._("Today")},
                {'key': 'last_month', 'label': self.env._("End of last month")},
                {'key': 'last_quarter', 'label': self.env._("End of last quarter")},
                {'key': 'this_year', 'label': self.env._("End of this year")},
                {'key': 'last_year', 'label': self.env._("End of last year")},
            ]
        return [
            {'key': 'this_month', 'label': self.env._("This month")},
            {'key': 'this_quarter', 'label': self.env._("This quarter")},
            {'key': 'this_year', 'label': self.env._("This year")},
            {'key': 'today', 'label': self.env._("Today")},
            {'key': 'last_month', 'label': self.env._("Last month"), 'separator': True},
            {'key': 'last_quarter', 'label': self.env._("Last quarter")},
            {'key': 'last_year', 'label': self.env._("Last year")},
        ]

    @api.model
    def _om_year_dates(self, day):
        """(first, last) day of the year ``day`` is in; a report may use another year (fiscal)."""
        return date(day.year, 1, 1), date(day.year, 12, 31)

    @api.model
    def _om_preset_dates(self, preset, today):
        """(date_from, date_to) of a named period."""
        if preset == 'today':
            return today, today
        if preset in ('this_month', 'last_month'):
            start = today.replace(day=1)
            if preset == 'last_month':
                start -= relativedelta(months=1)
            return start, start + relativedelta(months=1, days=-1)
        if preset in ('this_quarter', 'last_quarter'):
            start = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
            if preset == 'last_quarter':
                start -= relativedelta(months=3)
            return start, start + relativedelta(months=3, days=-1)
        if preset in ('this_year', 'last_year'):
            start, end = self._om_year_dates(today)
            if preset == 'last_year':
                start, end = self._om_year_dates(start - timedelta(days=1))
            return start, end
        return False, False

    @api.model
    def _om_period(self, options):
        """(date_from, date_to) of the options; date_from is False for 'as of' reports."""
        today = fields.Date.context_today(self)
        if options['date_preset'] == 'custom':
            date_to = fields.Date.to_date(options.get('date_to')) or today
            date_from = fields.Date.to_date(options.get('date_from')) or date_to.replace(day=1)
            if date_from > date_to:
                date_from, date_to = date_to, date_from
        else:
            date_from, date_to = self._om_preset_dates(options['date_preset'], today)
        if self._report_date_mode == 'as_of':
            return False, date_to
        return date_from, date_to

    @api.model
    def _om_format_date(self, value):
        return value and fields.Date.to_date(value).strftime(
            self.env['res.lang']._get_data(code=self.env.lang or 'en_US').date_format or '%m/%d/%Y')

    @api.model
    def _om_period_label(self, options):
        """The period, as the column groups and the subtitle print it."""
        if self._report_date_mode == 'none' or not options.get('date_to'):
            return ''
        if self._report_date_mode == 'as_of' or not options.get('date_from'):
            return self.env._("As of %s", self._om_format_date(options['date_to']))
        return self.env._("%(start)s - %(end)s", start=self._om_format_date(options['date_from']),
                          end=self._om_format_date(options['date_to']))

    @api.model
    def _om_subtitle(self, options):
        """One line saying what the report shows, for the screen, the PDF and the Excel file."""
        if self._report_date_mode == 'none':
            return ''
        if self._report_date_mode == 'as_of':
            return self._om_period_label(options)
        return self.env._("From %(start)s to %(end)s", start=self._om_format_date(options['date_from']),
                          end=self._om_format_date(options['date_to']))

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @api.model
    def _om_compares(self):
        """Whether the report can be compared with earlier periods."""
        return bool(self._report_compare) or (bool(self._report_compare_keys) and self._report_date_mode != 'none')

    @api.model
    def _om_compare_choices(self):
        return [
            {'key': 'previous_period', 'label': self.env._("Previous period")},
            {'key': 'previous_year', 'label': self.env._("Same period last year")},
        ]

    @api.model
    def _om_all_compare_choices(self):
        """The comparisons of the report, then a period of the user's choice."""
        return self._om_compare_choices() + [{'key': 'custom', 'label': self.env._("Custom dates")}]

    @api.model
    def _om_compare_periods(self, options):
        """The periods compared with, nearest first: [{'date_from', 'date_to', 'label'}]."""
        if not options.get('compare'):
            return []
        if options['compare'] == 'custom':
            if not options.get('compare_date_to') or (
                    self._report_date_mode == 'range' and not options.get('compare_date_from')):
                return []
            period = {**options, 'date_preset': 'custom', 'date_from': options.get('compare_date_from') or False,
                      'date_to': options['compare_date_to']}
            return [{'date_from': period['date_from'], 'date_to': period['date_to'],
                     'label': self._om_period_label(period)}]
        periods = []
        current = dict(options)
        for _index in range(options['compare_periods']):
            current = self._om_previous_period(current, options['compare'])
            periods.append({'date_from': current['date_from'], 'date_to': current['date_to'],
                            'label': self._om_period_label(current)})
        return periods

    @api.model
    def _om_previous_period(self, options, how):
        date_to = fields.Date.to_date(options['date_to'])
        date_from = fields.Date.to_date(options['date_from']) if options.get('date_from') else False
        if how == 'previous_year':
            new_from, new_to = date_from and date_from - relativedelta(years=1), date_to - relativedelta(years=1)
        elif not date_from:
            # as of: the end of the month before, or the same day a month earlier
            last_of_month = (date_to + timedelta(days=1)).day == 1
            new_to = date_to.replace(day=1) - timedelta(days=1) if last_of_month else date_to - relativedelta(months=1)
            new_from = False
        else:
            months = next((n for n in (1, 3, 6, 12) if date_from.day == 1
                           and date_from + relativedelta(months=n, days=-1) == date_to), 0)
            if months:
                new_from, new_to = date_from - relativedelta(months=months), date_from - timedelta(days=1)
            else:
                length = (date_to - date_from).days + 1
                new_from, new_to = date_from - timedelta(days=length), date_from - timedelta(days=1)
        return {**options, 'date_preset': 'custom',
                'date_from': new_from and fields.Date.to_string(new_from), 'date_to': fields.Date.to_string(new_to)}

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    @api.model
    def _om_get_columns(self, options):
        """[{'key', 'label', 'type', 'group', 'aggregate', 'visible', 'optional', 'detail_only', 'help'}]

        type: char, date, datetime, monetary, float, int, percent, ratio (2.35), days
        (45.2 days); a line may give a figure another type with 'types'. ``group``
        puts the column under a header spanning the columns of the same group
        (Initial Balance: Debit, Credit). ``aggregate: 'sum'`` sums the column
        on groups and on the total when the engine groups rows. A column with
        ``optional: False`` is always shown; ``visible: False`` hides it until
        the user picks it in the Columns menu. ``blank_zero`` leaves a zero
        blank on the detail lines (the debit of a credit entry). ``drill``
        makes the figures of the column open what makes them, on the lines
        that have ``drill`` (see _om_cell_action).
        """
        return []

    @api.model
    def _om_columns(self, options):
        columns = self._om_get_columns(options)
        if options.get('compare') and self._report_compare_keys:
            compared = []
            for column in columns:
                compared.append(column)
                if column['key'] in self._report_compare_keys:
                    compared += self._om_compare_columns(column, options)
            columns = compared
        # the choice of the user: {'shown': [keys], 'hidden': [keys], 'order': [keys]}; a column
        # neither shown nor hidden (one added since, by a comparison...) keeps its default
        chosen = options.get('columns') or {}
        if isinstance(chosen, list):
            # the visible columns, as the choice was kept before; the columns of a comparison stay
            # shown unless the list names some of them
            compared = {c['compare_of'] for c in columns if c.get('compare_of') and c['key'] in chosen}
            chosen = {'shown': chosen, 'hidden': [
                c['key'] for c in columns if c['key'] not in chosen
                and (not c.get('compare_of') or c['compare_of'] in compared)]}
        shown, hidden = set(chosen.get('shown') or []), set(chosen.get('hidden') or [])
        order = {key: index for index, key in enumerate(chosen.get('order') or [])}
        for column in columns:
            column.setdefault('type', 'char')
            column.setdefault('group', False)
            column.setdefault('aggregate', False)
            column.setdefault('optional', True)
            column.setdefault('visible', True)
            column.setdefault('detail_only', False)
            column.setdefault('blank_zero', False)
            column.setdefault('drill', False)
            column.setdefault('sortable', bool(self._report_group_by) and not column['detail_only'])
            column['label'] = str(column['label'])
            column['bar'] = bool(self._report_bar_column) and column['key'] == self._report_bar_column
            if column['group']:
                column['group'] = str(column['group'])
            if column['optional'] and column['key'] in shown:
                column['visible'] = True
            elif column['optional'] and column['key'] in hidden:
                column['visible'] = False
        if order:
            natural = {column['key']: index for index, column in enumerate(columns)}
            columns.sort(key=lambda c: (order.get(c['key'], len(order) + natural[c['key']])))
        return columns

    @api.model
    def _om_compare_suffix(self, index):
        """The suffix of the keys of the period compared with ``index`` (0 the nearest)."""
        return '_cmp' if not index else '_cmp%s' % (index + 1)

    @api.model
    def _om_compare_columns(self, column, options):
        """The columns added after a compared column: one per period compared with, then the change
        and the change in % against the nearest one."""
        periods = self._om_compare_periods(options)
        named = len(periods) == 1 and options['compare'] in ('previous_period', 'previous_year')
        base = {'compare_of': column['key'], 'optional': True, 'visible': True, 'group': column.get('group', False),
                'sortable': column.get('sortable', True)}
        columns = []
        for index, period in enumerate(periods):
            if named:
                label = self.env._("Previous") if options['compare'] == 'previous_period' else self.env._("Last Year")
            else:
                label = period['label']
            columns.append({**base, 'key': column['key'] + self._om_compare_suffix(index),
                            'label': '%s (%s)' % (column['label'], label), 'type': column['type'],
                            'digits': column.get('digits'), 'aggregate': 'sum', 'help': period['label']})
        if periods:
            columns += [
                {**base, 'key': column['key'] + '_delta', 'label': 'Δ %s' % column['label'],
                 'type': column['type'], 'digits': column.get('digits'), 'aggregate': 'sum'},
                {**base, 'key': column['key'] + '_pct', 'label': 'Δ %', 'type': 'percent'},
            ]
        for compare_column in columns:
            if compare_column.get('digits') is None:
                compare_column.pop('digits', None)
        return columns

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    @api.model
    def _om_line(self, line_id, name, values=None, parent_id=False, level=0, kind='leaf', has_children=False,
                 open_record=False, drill=False, links=None, count=0, **extra):
        """A line of the report. ``open_record`` is (model, id) of the record the line opens."""
        line = {
            'id': line_id,
            'parent_id': parent_id,
            'level': level,
            'kind': kind,
            'name': name or '',
            'values': values or {},
            'has_children': has_children,
            'count': count,
            'open': {'res_model': open_record[0], 'res_id': open_record[1]} if open_record else False,
            'drill': drill,
            'links': links or [],
        }
        line.update(extra)
        return line

    @api.model
    def _om_link(self, report_model, label, options, icon=False):
        """A link to another report, opened with ``options`` (merged into the current dates)."""
        report = self.env[report_model]
        return {'model': report_model, 'label': str(label), 'icon': icon or report._report_icon, 'options': options}

    @api.model
    def _om_compute(self, options):
        """What the report computed for ``options``, kept a while (see _om_compute_cached).

        By default: the rows of _om_get_rows grouped as options['group_by'] says,
        with the rows of the periods compared with when the report compares sums
        (_report_compare_keys). ``all_rows`` are the rows before the filters, for
        the key figures.
        """
        columns = self._om_columns(options)
        all_rows = self._om_enrich_rows(self._om_get_rows(options), options)
        rows = self._om_filter_rows(all_rows, options, columns)
        compare_rows = self._om_compare_rows(options, rows) if options.get('compare') else []
        tree, total = self._om_build_tree(rows + compare_rows, options, columns)
        if options['search']:
            tree = self._om_search_tree(tree, options['search'])
        self._om_sort_nodes(tree, options)
        return {'tree': tree, 'total': total, 'rows': rows, 'all_rows': all_rows}

    @api.model
    def _om_compare_rows(self, options, rows):
        """The rows of the periods compared with, carrying only their sums under the keys of the
        period ('<key>_cmp', '<key>_cmp2'...), so that they fall in the same groups as the rows of
        the period and add up with them."""
        if not self._report_compare_keys:
            return []
        match = self._om_compare_match_keys(options)
        shown = None
        if options['kpi_filter'] or options['search']:
            # only for what the rows of the period show
            shown = {tuple(row.get(key) for key in match) for row in rows}
        precision = self._om_zero_precision()
        result = []
        for index, period in enumerate(self._om_compare_periods(options)):
            suffix = self._om_compare_suffix(index)
            period_options = {**options, 'date_preset': 'custom', 'date_from': period['date_from'],
                              'date_to': period['date_to'], 'compare': False, 'kpi_filter': False, 'search': ''}
            sum_keys = [c['key'] for c in self._om_columns(period_options)
                        if c['aggregate'] == 'sum' and c['type'] in NUMERIC_TYPES]
            for row in self._om_enrich_rows(self._om_get_rows(period_options), period_options):
                new = {k: v for k, v in row.items() if k.endswith('_id') or k in self._om_compare_carried()}
                new.update({key + suffix: row.get(key) or 0.0 for key in sum_keys})
                new['_cmp'] = True
                if options.get('hide_zero') and not any(abs(new[key + suffix]) >= precision for key in sum_keys):
                    continue
                if shown is not None and tuple(new.get(key) for key in match) not in shown:
                    continue
                result.append(new)
        return result

    @api.model
    def _om_compare_match_keys(self, options):
        """The keys of a row telling which rows of a period compared with belong to the rows shown."""
        return [dim + '_id' for dim in options['group_by']]

    @api.model
    def _om_zero_precision(self):
        """Below this, a figure is a zero (to hide the zero lines)."""
        return 1e-6

    @api.model
    def _om_compare_carried(self):
        """Keys of a row, besides its dimensions, kept on the rows of the periods compared with."""
        return ()

    @api.model
    def _om_compare_node(self, node, options):
        """The change and the change in % of the compared sums, against the nearest period."""
        if not options.get('compare') or not self._report_compare_keys:
            return
        values = node['values']
        for key in self._report_compare_keys:
            current, previous = values.get(key) or 0.0, values.get(key + '_cmp') or 0.0
            values[key + '_delta'] = current - previous
            values[key + '_pct'] = (current - previous) / abs(previous) * 100 if previous else False

    @api.model
    def _om_lines(self, data, options, parent_id=False, offset=0, limit=PAGE_SIZE):
        """(lines under ``parent_id``, how many more there are); the top lines without one.
        ``limit`` 0 or None for all of them."""
        if not parent_id:
            nodes = data['tree']
        else:
            node = self._om_find_node(data['tree'], parent_id)
            if not node:
                return [], 0
            if not node['children']:
                if node['leaf'] and self._om_has_details(options):
                    return self._om_page(self._om_detail_lines(node, options), offset, limit)
                return [], 0
            nodes = node['children']
        page, more = self._om_page(nodes, offset, limit)
        return [self._om_node_line(node, options) for node in page], more

    @api.model
    def _om_page(self, items, offset, limit):
        page = items[offset:offset + limit] if limit else items[offset:]
        return page, max(len(items) - offset - len(page), 0)

    @api.model
    def _om_total(self, data, options):
        """The total line of the table, or False."""
        total = data.get('total')
        if not total:
            return False
        return self._om_line('total', total.get('name') or self.env._("Total"), total['values'], kind='total')

    @api.model
    def _om_line_action(self, options, line_id):
        """The action a line with ``drill`` opens (journal items behind a figure...)."""
        return False

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        """The action of a figure of a drillable column: what makes this one figure (the entries
        of its period, of its analytic account...). The action of the line by default."""
        return self._om_line_action(options, line_id)

    @api.model
    def _om_line_button(self, options, line_id, key):
        """The action of the button ``key`` of a line (see the 'actions' of a line), or False."""
        return False

    @api.model
    def _om_note_scope(self, options, column_key):
        """(column without its period, date_from, date_to) of the figures of a column: what a note
        on one of them is attached to."""
        return column_key, options.get('date_from') or False, options.get('date_to') or False

    @api.model
    def _om_notes_by_line(self, options, line_ids):
        """{line id: {column key: [note values]}} of the notes on the figures of these lines."""
        if not line_ids:
            return {}
        scopes = {}
        for column in self._om_columns(options):
            if column['type'] in NUMERIC_TYPES:
                base, date_from, date_to = self._om_note_scope(options, column['key'])
                scopes.setdefault((base, str(date_from or ''), str(date_to or '')), []).append(column['key'])
        notes = self.env['om.report.note'].sudo().search([
            ('report_model', '=', self._name), ('line_key', 'in', list(line_ids)),
            ('company_id', 'in', self.env.companies.ids)])
        result = {}
        for note in notes:
            key = (note.column_key, str(note.date_from or ''), str(note.date_to or ''))
            for column_key in scopes.get(key, []):
                result.setdefault(note.line_key, {}).setdefault(column_key, []).extend(note._om_values())
        return result

    @api.model
    def _om_attach_notes(self, options, lines):
        """Copies of the lines with their notes: the lines may be those kept in the cache, shared by
        the requests that follow, and a note deleted since must not stay on them."""
        notes = self._om_notes_by_line(options, [line['id'] for line in lines])
        result = []
        for line in lines:
            line = dict(line)
            line.pop('notes', None)
            if line['id'] in notes:
                line['notes'] = notes[line['id']]
            result.append(line)
        return result

    @api.model
    def _om_note_domain(self, options, line_id, column_key):
        base, date_from, date_to = self._om_note_scope(options, column_key)
        return [('report_model', '=', self._name), ('line_key', '=', line_id), ('column_key', '=', base),
                ('date_from', '=', date_from or False), ('date_to', '=', date_to or False),
                ('company_id', 'in', self.env.companies.ids)]

    @api.model
    def _om_export_extra(self, options):
        """More for the exported files: 'recipient' (a partner whose address heads the PDF),
        'note' (a text printed under the table)."""
        return {}

    # ------------------------------------------------------------------
    # Grouping rows
    # ------------------------------------------------------------------

    @api.model
    def _om_dimensions(self):
        """How rows can be grouped: {key: {'label', 'model', 'icon'}}; a row carries '<key>_id'.
        A dimension without a model gives a 'selection': {value: label}."""
        return {}

    @api.model
    def _om_get_rows(self, options):
        """The rows of the report: dicts with '<dimension>_id' keys and the column values."""
        return []

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options.get('hide_zero'):
            keys = [c['key'] for c in columns if c['aggregate'] == 'sum' and c['type'] in NUMERIC_TYPES]
            precision = self._om_zero_precision()
            rows = [r for r in rows if any(abs(r.get(k) or 0.0) >= precision for k in keys)]
        if options.get('kpi_filter'):
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_enrich_rows(self, rows, options):
        """The rows completed with what derives from them (the category of a product...)."""
        return rows

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        """The rows of a key figure, chart bar or matrix cell (``kpi`` is its 'filter')."""
        return rows

    @api.model
    def _om_names(self, dim, ids):
        if not ids:
            return {}
        dimension = self._om_dimensions()[dim]
        if 'selection' in dimension:
            return {key: str(label) for key, label in dimension['selection'].items() if key in ids}
        records = self.env[dimension['model']].with_context(active_test=False).browse(ids).exists()
        return {r.id: r.display_name for r in records}

    @api.model
    def _om_empty_name(self, dim):
        return self.env._("None")

    @api.model
    def _om_build_tree(self, rows, options, columns):
        """Nested nodes: {'id', 'dim', 'res_id', 'name', 'rows', 'values', 'children', 'leaf'}."""
        group_by = options['group_by']
        names = {dim: self._om_names(dim, list({r.get(dim + '_id') for r in rows if r.get(dim + '_id')}))
                 for dim in group_by}
        sum_keys = [c['key'] for c in columns if c['aggregate'] == 'sum']

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
                    'id': node_id, 'parent_id': parent_id, 'level': level, 'dim': dim, 'res_id': res_id,
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
        total = {'id': 'total', 'name': self.env._("Total"), 'rows': [r for r in rows if not r.get('_cmp')],
                 'dim': False, 'res_id': False, 'parent_id': False, 'level': 0,
                 'values': {k: sum(r.get(k) or 0.0 for r in rows) for k in sum_keys}, 'children': [], 'leaf': False}
        self._om_finalize_node(total, options)
        self._om_compare_node(total, options)
        return tree, total

    @api.model
    def _om_finalize_node(self, node, options):
        """Set the values of a node that are not sums (ratios, averages...)."""

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
                # the values of a selection in the order the report gives them (Class A, B, C...)
                selection = dimensions.get(node['dim'], {}).get('selection')
                if selection and node['res_id'] in selection:
                    return (False, '%06d' % list(selection).index(node['res_id']))
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

    @api.model
    def _om_find_node(self, nodes, node_id):
        for node in nodes:
            if node['id'] == node_id:
                return node
            if node_id.startswith(node['id'] + '|'):
                return self._om_find_node(node['children'], node_id)
        return None

    @api.model
    def _om_node_line(self, node, options):
        dimension = self._om_dimensions().get(node['dim'], {})
        line = self._om_line(
            node['id'], node['name'], node['values'], parent_id=node['parent_id'], level=node['level'],
            kind='leaf' if node['leaf'] else 'group',
            has_children=bool(node['children']) or (node['leaf'] and self._om_has_details(options)),
            count=len(node['children']), dim=node['dim'], icon=dimension.get('icon'),
            links=self._om_node_links(node, options),
        )
        line['open'] = self._om_node_open(node, options)
        if self._report_expand_default and node['children']:
            line['unfolded'] = True
        return line

    @api.model
    def _om_node_open(self, node, options):
        """{'res_model', 'res_id'} of the record a line of a group opens, or False."""
        model = self._om_dimensions().get(node['dim'], {}).get('model')
        if not model or not node['res_id']:
            return False
        return {'res_model': model, 'res_id': node['res_id']}

    @api.model
    def _om_has_details(self, options):
        """Whether the leaves have detail lines (_om_detail_lines)."""
        return self._report_has_details

    @api.model
    def _om_node_links(self, node, options):
        return []

    @api.model
    def _om_detail_lines(self, node, options):
        """Detail lines of a leaf, built with _om_line(kind='detail')."""
        return []

    # ------------------------------------------------------------------
    # Key figures and chart
    # ------------------------------------------------------------------

    @api.model
    def _om_get_kpis(self, data, options):
        """The key figures above the table: [{'key', 'label', 'value', 'type', 'icon', 'tone',
        'filter', 'compare_key'}]. A figure with a ``filter`` narrows the report down to its rows
        when clicked (see _om_kpi_filter_rows); one whose key (or ``compare_key``) is a compared
        sum shows the figure of the period compared with. tone: neutral, success, warning, danger,
        info."""
        return []

    @api.model
    def _om_compare_kpis(self, kpis, data, options):
        """The key figures with the figure of the nearest period compared with and the change in %."""
        if not options.get('compare') or not self._report_compare_keys or not data.get('total'):
            return kpis
        total = data['total']['values']
        for kpi in kpis:
            key = kpi.get('compare_key', kpi['key'])
            if key in self._report_compare_keys:
                kpi['previous'] = total.get(key + '_cmp') or 0.0
                kpi['delta_pct'] = total.get(key + '_pct')
        return kpis

    @api.model
    def _om_get_chart(self, data, options):
        """A chart drawn above the table, or None.

        {'type': 'bar' | 'donut', 'title', 'value_type', 'items': [{'key', 'label', 'value', 'tone',
        'filter', 'caption'}]} or {'type': 'matrix', 'title', 'rows': [{'key', 'label'}], 'cols':
        [{'key', 'label'}], 'cells': {row key: {col key: {'value', 'caption', 'tone', 'filter'}}}}. An
        item or a cell with a filter narrows the report down like a key figure.
        """
        return None

    @api.model
    def _om_top_items(self, rows, key, label_key='product_id', limit=10, tone=None):
        """The ``limit`` largest sums of ``key`` by ``label_key`` (a dimension), as chart items."""
        totals = defaultdict(float)
        for row in rows:
            if row.get(label_key):
                totals[row[label_key]] += row.get(key) or 0.0
        top = sorted(((v, k) for k, v in totals.items() if v > 0), reverse=True)[:limit]
        names = self._om_names(label_key[:-3], [k for _v, k in top])
        return [{'key': str(k), 'label': names.get(k, ''), 'value': v, 'tone': tone} for v, k in top]

    @api.model
    def _om_digits(self):
        """The decimals of the 'float' figures that do not say theirs (key figures, chart)."""
        return 2

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Public API, called by the screen
    # ------------------------------------------------------------------

    @api.model
    def om_get_report(self, options=None, expanded=None, auto_unfold=False):
        """Everything the screen needs to draw the report.

        ``expanded``: ids of the unfolded lines; their children come too, so the
        report reopens the way it was left. ``auto_unfold``: unfold the lines
        that ask for it (``unfolded``), when the report is opened afresh.
        """
        self._om_check_access()
        options = self._om_normalize_options(options)
        self = self._om_prepare(options)
        data = self._om_compute_cached(options, fresh=True)
        lines, more = self._om_lines(data, options, False, 0, self._report_page_size)
        lines = self._om_attach_notes(options, lines)
        children = {}
        todo = list(expanded or [])
        if auto_unfold:
            todo += [line['id'] for line in lines if line.get('unfolded') and line['has_children']]
        while todo:
            line_id = todo.pop(0)
            if line_id in children:
                continue
            child_lines, child_more = self._om_lines(data, options, line_id, 0, self._report_page_size)
            if child_lines:
                child_lines = self._om_attach_notes(options, child_lines)
                children[line_id] = {'lines': child_lines, 'more': child_more}
                if auto_unfold:
                    todo += [line['id'] for line in child_lines if line.get('unfolded') and line['has_children']]
        dimensions = self._om_dimensions()
        return {
            'model': self._name,
            'name': self._om_report_title(),
            'app': self._report_app,
            'icon': self._report_icon,
            'description': str(self._report_description or ''),
            'options': options,
            'date_mode': self._report_date_mode,
            'date_presets': self._om_date_presets(),
            'filters': self._om_filters_meta(),
            'toggles': [{**t, 'label': str(t['label'])} for t in self._om_toggles()],
            'choices': self._om_choices_meta(),
            'numbers': [{**n, 'label': str(n['label'])} for n in self._om_numbers()],
            'group_by': [{'key': key, 'label': str(dimensions[key]['label']), 'icon': dimensions[key].get('icon')}
                         for key in self._report_group_by if key in dimensions],
            'compare_choices': self._om_all_compare_choices() if self._om_compares() else [],
            'rounding': self._om_rounding(options),
            'compare_label': ', '.join(p['label'] for p in self._om_compare_periods(options)),
            'columns': self._om_columns(options),
            'name_label': self._om_name_label(options),
            'lines': lines,
            'more': more,
            'children': children,
            'expanded': list(children),
            'total': self._om_total(data, options),
            'currency_id': self._om_currency().id,
            'subtitle': self._om_subtitle(options),
            'page_size': self._report_page_size,
            'kpis': self._om_compare_kpis(self._om_get_kpis(data, options), data, options),
            'chart': self._om_get_chart(data, options),
            'digits': self._om_digits(),
        }

    @api.model
    def om_get_children(self, options, line_id, offset=0):
        self._om_check_access()
        options = self._om_normalize_options(options)
        self = self._om_prepare(options)
        data = self._om_compute_cached(options)
        lines, more = self._om_lines(data, options, line_id or False, int(offset or 0), self._report_page_size)
        return {'lines': self._om_attach_notes(options, lines), 'more': more}

    @api.model
    def om_open_line(self, options, line_id):
        """The action of a line that has ``drill``."""
        self._om_check_access()
        options = self._om_normalize_options(options)
        return self._om_prepare(options)._om_line_action(options, line_id) or False

    @api.model
    def om_open_cell(self, options, line_id, column_key):
        """The action of a figure of a drillable column."""
        self._om_check_access()
        options = self._om_normalize_options(options)
        if column_key not in {column['key'] for column in self._om_columns(options) if column['drill']}:
            return False
        return self._om_prepare(options)._om_cell_action(options, line_id, column_key) or False

    @api.model
    def om_get_notes(self, options, line_id, column_key):
        """The notes on one figure."""
        self._om_check_access()
        options = self._om_normalize_options(options)
        report = self._om_prepare(options)
        return self.env['om.report.note'].sudo().search(
            report._om_note_domain(options, line_id, column_key))._om_values()

    @api.model
    def om_save_note(self, options, line_id, column_key, text, note_id=False):
        """Add a note to a figure, or change one of the user's own."""
        self._om_check_access()
        options = self._om_normalize_options(options)
        report = self._om_prepare(options)
        text = (text or '').strip()
        # the notes are reached through the report only, whose access is checked above: a user changes
        # their own notes of their companies, and nothing else
        Note = self.env['om.report.note'].sudo()
        note = Note.browse(note_id).exists() if note_id else Note
        if note:
            if (note.user_id == self.env.user and note.report_model == self._name
                    and note.company_id in self.env.companies):
                if text:
                    note.note = text
                else:
                    note.unlink()
        elif text:
            base, date_from, date_to = report._om_note_scope(options, column_key)
            Note.create({'report_model': self._name, 'line_key': line_id, 'column_key': base,
                         'date_from': date_from or False, 'date_to': date_to or False, 'note': text,
                         'user_id': self.env.uid, 'company_id': self.env.company.id})
        return Note.search(report._om_note_domain(options, line_id, column_key))._om_values()

    @api.model
    def om_delete_note(self, note_id):
        """Delete one of the user's own notes."""
        self._om_check_access()
        note = self.env['om.report.note'].sudo().browse(note_id).exists()
        if note and note.user_id == self.env.user and note.report_model == self._name:
            note.unlink()
        return True

    @api.model
    def om_line_button(self, options, line_id, key):
        """The action of a button of a line."""
        self._om_check_access()
        options = self._om_normalize_options(options)
        return self._om_prepare(options)._om_line_button(options, line_id, key) or False

    @api.model
    def _om_currency(self):
        return self.env.company.currency_id

    @api.model
    def _om_filters_meta(self):
        return [{'icon': 'filter_alt', 'domain': [], **spec, 'label': str(spec['label'])}
                for spec in self._om_filters()]

    @api.model
    def _om_choices_meta(self):
        return [{**spec, 'label': str(spec['label']), 'menu': spec.get('menu', 'options'),
                 'choices': [[value, str(label)] for value, label in spec['choices']]}
                for spec in self._om_all_choices()]

    @api.model
    def _om_filter_summary(self, options):
        """[(label, value)] of what the report was run with, printed above the exported table."""
        summary = []
        subtitle = self._om_subtitle(options)
        if subtitle:
            summary.append((self.env._("Period"), subtitle))
        compare = self._om_compare_periods(options)
        if compare:
            summary.append((self.env._("Compared with"), ', '.join(p['label'] for p in compare)))
        for spec in self._om_filters():
            ids = options.get(spec['key'])
            if ids:
                records = self.env[spec['model']].with_context(active_test=False).browse(ids).exists()
                summary.append((str(spec['label']), ', '.join(records.mapped('display_name'))))
        for spec in self._om_all_choices():
            labels = dict(spec['choices'])
            if spec.get('summary', True):
                summary.append((str(spec['label']), str(labels.get(options[spec['key']], ''))))
        active = [str(spec['label']) for spec in self._om_toggles() if options.get(spec['key'])]
        if active:
            summary.append((self.env._("Options"), ', '.join(active)))
        if options['group_by']:
            dims = self._om_dimensions()
            summary.append((self.env._("Grouped by"), ' > '.join(str(dims[g]['label']) for g in options['group_by'])))
        if options['search']:
            summary.append((self.env._("Search"), options['search']))
        return summary

    @api.model
    def _om_name_label(self, options):
        if self._report_name_label:
            return str(self._report_name_label)
        if options['group_by']:
            dims = self._om_dimensions()
            return ' / '.join(str(dims[g]['label']) for g in options['group_by'])
        return ''

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def om_export_data(self, options, expanded=None, expand_all=False):
        """The lines as printed: the top lines and, under them, the children of
        the unfolded lines (or of every line)."""
        self._om_check_access()
        options = self._om_normalize_options(options)
        self = self._om_prepare(options)
        data = self._om_compute_cached(options)
        expanded = set(expanded or [])
        flat = []

        def walk(parent_id):
            lines, _more = self._om_lines(data, options, parent_id, 0, 0)
            for line in lines:
                if len(flat) >= EXPORT_LIMIT:
                    return
                flat.append(line)
                if line['has_children'] and (expand_all or line['id'] in expanded):
                    walk(line['id'])

        walk(False)
        flat = self._om_attach_notes(options, flat)
        columns_by_key = {column['key']: column for column in self._om_columns(options)}
        notes = [{'line': line['name'], 'column': columns_by_key[key]['label'],
                  'group': columns_by_key[key].get('group') or '', 'note': note['note'], 'author': note['author']}
                 for line in flat for key, column_notes in (line.get('notes') or {}).items()
                 if key in columns_by_key for note in column_notes]
        return {
            'notes': notes,
            'title': self._om_report_title(),
            'subtitle': self._om_subtitle(options),
            'filters': self._om_filter_summary(options),
            'columns': [c for c in self._om_columns(options) if c['visible']],
            'name_label': self._om_name_label(options),
            'lines': flat,
            'total': self._om_total(data, options),
            'currency': self._om_currency(),
            'rounding': self._om_rounding(options),
            'company': self.env.company,
            'options': options,
            'kpis': self._om_compare_kpis(self._om_get_kpis(data, options), data, options),
            'digits': self._om_digits(),
            'recipient': False,
            'note': '',
            **self._om_export_extra(options),
        }
