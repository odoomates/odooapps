""" Build the JSON of an Odoo spreadsheet dashboard from Python.

The dashboards of the Dashboards app are o-spreadsheet workbooks stored as JSON. Community Odoo cannot edit them,
so they are written here in code: cells, pivots, lists, charts and global filters, then dumped next to the module.
The dashboards are written in the format of the spreadsheet library of Odoo 19.0 (version 18.5.10), then brought
back to the one of Odoo 18.0 by `to_odoo_18` (version 22, Odoo data version 12): the steps of the migrations of the
spreadsheet library of 19.0 after 18.0.4, the version 22, undone.

Not loaded by Odoo: run the build script of the module to regenerate the files.
"""
import json
import uuid

VERSION = '18.5.10'
# the data versions of the spreadsheet library of Odoo 18.0: the newest one it reads
ODOO_18_VERSION = 22
ODOO_18_ODOO_VERSION = 12

# the default values of the relative date filters of 19.0, under their name of 18.0
ODOO_18_DATE_DEFAULTS = {
    'last_7_days': 'last_week',
    'last_30_days': 'last_month',
    'last_90_days': 'last_three_months',
    'last_12_months': 'last_year',
}

TEAL = '#01666B'
GREY = '#434343'
GREEN = '#00A04A'
RED = '#DC6965'
BACKGROUND = '#F9FAFB'

PERCENT_FORMAT = '0.0%'
RATIO_FORMAT = '0.00'
INTEGER_FORMAT = '#,##0'


def stable_id(*parts):
    """ The same id on every build, so that the files only change when the dashboards do. """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'om_spreadsheet_account/' + '/'.join(str(p) for p in parts)))


def col_name(index):
    """ 0 -> A, 25 -> Z, 26 -> AA """
    name = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def cell_ref(col, row):
    """ Zero-based column and row to A1 """
    return f'{col_name(col)}{row + 1}'


def quote(text):
    return '"%s"' % str(text).replace('"', '""')


def label(text):
    """ A translatable label cell """
    return '=_t(%s)' % quote(text)


class Sheet:

    def __init__(self, workbook, name, cols=26, rows=100, sheet_id=None):
        self.workbook = workbook
        self.id = sheet_id or stable_id(workbook.key, 'sheet', name)
        self.name = name
        self.col_number = cols
        self.row_number = rows
        self.cells = {}
        self.styles = {}
        self.formats = {}
        self.borders = {}
        self.col_sizes = {}
        self.row_sizes = {}
        self.merges = []
        self.figures = []
        self.conditional_formats = []
        self.background = None

    @property
    def ref_name(self):
        return "'%s'" % self.name if not self.name.isalnum() else self.name

    def ref(self, col, row, absolute=False, sheet=True):
        a1 = cell_ref(col, row)
        if absolute:
            a1 = '$%s$%s' % (col_name(col), row + 1)
        return f'{self.ref_name}!{a1}' if sheet else a1

    def range(self, col, row, col_to, row_to):
        return f'{self.ref_name}!{cell_ref(col, row)}:{cell_ref(col_to, row_to)}'

    def set(self, col, row, value, style=None, fmt=None, border=None):
        a1 = cell_ref(col, row)
        if value is not None:
            self.cells[a1] = value if isinstance(value, str) else str(value)
        if style:
            self.styles[a1] = self.workbook.style_id(style)
        if fmt:
            self.formats[a1] = self.workbook.format_id(fmt)
        if border:
            self.borders[a1] = self.workbook.border_id(border)
        return self.ref(col, row)

    def add_figure(self, tag, data, x, y, width, height, figure_id):
        self.figures.append({
            'id': figure_id,
            'col': 0,
            'row': 0,
            'offset': {'x': x, 'y': y},
            'width': width,
            'height': height,
            'tag': tag,
            'data': data,
        })

    def scorecard(self, key, title, key_value, x, y, width=235, height=110, baseline=None, baseline_text=None,
                  baseline_mode='percentage'):
        figure_id = stable_id(self.workbook.key, 'figure', key)
        data = {
            'type': 'scorecard',
            'title': {'text': title, 'color': TEAL, 'bold': True},
            'background': '',
            'keyValue': key_value,
            'baselineColorDown': RED,
            'baselineColorUp': GREEN,
            'baselineMode': baseline_mode,
            'humanize': True,
            'chartId': figure_id,
        }
        if baseline:
            data['baseline'] = baseline
        if baseline_text:
            data['baselineDescr'] = {'text': baseline_text}
        self.add_figure('chart', data, x, y, width, height, figure_id)
        return figure_id

    def chart(self, key, chart_type, title, label_range, datasets, x, y, width, height, stacked=False,
              legend='top', extra=None):
        """ :param datasets: list of (data range, label, style) with style a dict, e.g. {'type': 'line'} """
        figure_id = stable_id(self.workbook.key, 'figure', key)
        data = {
            'type': chart_type,
            'title': {'text': title, 'color': TEAL, 'bold': True},
            'legendPosition': legend,
            'humanize': True,
            'labelRange': label_range,
            'dataSets': [
                {'dataRange': data_range, 'label': dataset_label, **(style or {})}
                for data_range, dataset_label, style in datasets
            ],
            'dataSetsHaveTitle': False,
            'chartId': figure_id,
        }
        if chart_type in ('bar', 'line', 'combo'):
            data['stacked'] = stacked
            data['aggregated'] = False
        if extra:
            data.update(extra)
        self.add_figure('chart', data, x, y, width, height, figure_id)
        return figure_id

    def odoo_chart(self, key, chart_type, title, model, measure, group_by, domain, x, y, width, height,
                   field_matching=None, action_xmlid=None, legend='top'):
        """ A chart of the data of a model, grouped like a graph view, shown in a carousel so that it follows the
        global filters. """
        figure_id = stable_id(self.workbook.key, 'figure', key)
        chart_id = stable_id(self.workbook.key, 'chart', key)
        definition = {
            'type': 'odoo_' + chart_type,
            'title': {},
            'legendPosition': legend,
            'humanize': True,
            'metaData': {
                'groupBy': group_by, 'measure': measure, 'order': None, 'resModel': model,
                'mode': 'pie' if chart_type == 'pie' else 'bar',
            },
            'searchParams': {
                'comparison': None, 'context': {}, 'domain': domain, 'groupBy': group_by, 'orderBy': [],
            },
            'cumulatedStart': False,
            'dataSets': [],
        }
        if chart_type in ('bar', 'line'):
            definition['stacked'] = False
        if action_xmlid:
            definition['actionXmlId'] = action_xmlid
        data = {
            'chartDefinitions': {chart_id: definition},
            'title': {'text': title, 'fontSize': 16, 'bold': True, 'color': TEAL},
            'items': [{'type': 'chart', 'chartId': chart_id}],
            'fieldMatching': {chart_id: {
                filter_id: {'chain': chain, 'type': field_type}
                for filter_id, (chain, field_type) in (field_matching or {}).items()
            }},
        }
        self.add_figure('carousel', data, x, y, width, height, figure_id)
        return figure_id

    def to_json(self):
        data = {
            'id': self.id,
            'name': self.name,
            'colNumber': self.col_number,
            'rowNumber': self.row_number,
            'rows': {str(k): {'size': v} for k, v in sorted(self.row_sizes.items())},
            'cols': {str(k): {'size': v} for k, v in sorted(self.col_sizes.items())},
            'merges': self.merges,
            'cells': self.cells,
            'styles': self.styles,
            'formats': self.formats,
            'borders': self.borders,
            'conditionalFormats': self.conditional_formats,
            'dataValidationRules': [],
            'figures': self.figures,
            'tables': [],
            'areGridLinesVisible': self.background is None,
            'isVisible': True,
            'headerGroups': {'ROW': [], 'COL': []},
            'comments': {},
        }
        if self.background:
            data['backgroundColor'] = self.background
        return data


class Workbook:

    def __init__(self, key):
        self.key = key
        self.sheets = []
        self._styles = []
        self._formats = []
        self._borders = []
        self.pivots = {}
        self.lists = {}
        self.global_filters = []
        self.link_references = {}
        self._list_columns = {}

    # -- registries of the workbook -----------------------------------------

    def _register(self, registry, value):
        if value not in registry:
            registry.append(value)
        return registry.index(value) + 1

    def style_id(self, style):
        return self._register(self._styles, style)

    def format_id(self, fmt):
        return self._register(self._formats, fmt)

    def border_id(self, border):
        return self._register(self._borders, border)

    def sheet(self, name, **kwargs):
        sheet = Sheet(self, name, **kwargs)
        self.sheets.append(sheet)
        return sheet

    # -- data sources --------------------------------------------------------

    def date_filter(self, key, label_text, default='this_year'):
        filter_id = stable_id(self.key, 'filter', key)
        self.global_filters.append({
            'id': filter_id, 'type': 'date', 'label': label_text, 'defaultValue': default,
        })
        return filter_id

    def text_filter(self, key, label_text, allowed_ranges, default):
        """ A filter picking one of the values of the given ranges, read by the formulas with ODOO.FILTER.VALUE """
        filter_id = stable_id(self.key, 'filter', key)
        self.global_filters.append({
            'id': filter_id, 'type': 'text', 'label': label_text, 'rangesOfAllowedValues': allowed_ranges,
            'defaultValue': {'operator': 'in', 'strings': [default]},
        })
        return filter_id

    def relation_filter(self, key, label_text, model, domain=None):
        filter_id = stable_id(self.key, 'filter', key)
        global_filter = {
            'id': filter_id, 'type': 'relation', 'label': label_text, 'modelName': model,
            'defaultValueDisplayNames': [],
        }
        if domain:
            global_filter['domainOfAllowedValues'] = domain
        self.global_filters.append(global_filter)
        return filter_id

    def pivot(self, name, model, domain, measures, rows=(), columns=(), field_matching=None, sorted_column=None,
              context=None):
        """ :param measures: field names, or (field name, aggregator)
            :param rows: field names, or (field name, granularity)
            :param field_matching: {filter id: (field chain, field type)} """
        pivot_id = str(len(self.pivots) + 1)

        def dimension(value):
            if isinstance(value, tuple):
                return {'fieldName': value[0], 'granularity': value[1]}
            return {'fieldName': value}

        def measure(value):
            if isinstance(value, tuple):
                return {'id': '%s:%s' % value, 'fieldName': value[0], 'aggregator': value[1]}
            return {'id': value, 'fieldName': value}

        pivot = {
            'type': 'ODOO',
            'id': pivot_id,
            'formulaId': pivot_id,
            'name': name,
            'model': model,
            'domain': domain,
            'context': context or {},
            'measures': [measure(m) for m in measures],
            'rows': [dimension(r) for r in rows],
            'columns': [dimension(c) for c in columns],
            'fieldMatching': {
                filter_id: {'chain': chain, 'type': field_type, **({'offset': 0} if field_type == 'date' else {})}
                for filter_id, (chain, field_type) in (field_matching or {}).items()
            },
        }
        if sorted_column:
            measure_name, order = sorted_column
            pivot['sortedColumn'] = {'measure': measure_name, 'order': order, 'domain': []}
        self.pivots[pivot_id] = pivot
        return pivot_id

    def odoo_list(self, name, model, domain, columns, order_by=(), field_matching=None, context=None):
        """ :param columns: (field name, label)
            :param order_by: (field name, ascending) """
        list_id = str(len(self.lists) + 1)
        self._list_columns[list_id] = list(columns)
        self.lists[list_id] = {
            'id': list_id,
            'name': name,
            'model': model,
            'domain': domain,
            'context': context or {},
            'columns': [field_name for field_name, _text in columns],
            'orderBy': [{'name': field_name, 'asc': ascending} for field_name, ascending in order_by],
            'fieldMatching': {
                filter_id: {'chain': chain, 'type': field_type, **({'offset': 0} if field_type == 'date' else {})}
                for filter_id, (chain, field_type) in (field_matching or {}).items()
            },
        }
        return list_id

    def link_menu(self, figure_id, menu_xmlid):
        """ A click on the figure opens the menu """
        self.link_references[figure_id] = menu_xmlid

    def list_table(self, sheet, col, row, list_id, rows, header_style=None):
        """ The records of a list, a header then one line per record: ODOO.LIST(list, position, field) returns one
        value. ODOO.LIST.HEADER of Odoo 18.0 takes no header text: the header is the label of the column. """
        for offset, (field_name, text) in enumerate(self._list_columns[list_id]):
            sheet.set(col + offset, row, label(text), header_style)
            for index in range(1, rows + 1):
                sheet.set(col + offset, row + index, '=ODOO.LIST(%s,%s,"%s")' % (list_id, index, field_name))

    # -- output ------------------------------------------------------------------

    def to_json(self):
        return {
            'version': VERSION,
            'sheets': [sheet.to_json() for sheet in self.sheets],
            'styles': {str(i + 1): style for i, style in enumerate(self._styles)},
            'formats': {str(i + 1): fmt for i, fmt in enumerate(self._formats)},
            'borders': {str(i + 1): border for i, border in enumerate(self._borders)},
            'revisionId': 'START_REVISION',
            'uniqueFigureIds': True,
            'settings': {'locale': {
                'name': 'English (US)', 'code': 'en_US', 'thousandsSeparator': ',', 'decimalSeparator': '.',
                'dateFormat': 'mm/dd/yyyy', 'timeFormat': 'hh:mm:ss', 'formulaArgSeparator': ',', 'weekStart': 7,
            }},
            'pivots': self.pivots,
            'pivotNextId': len(self.pivots) + 1,
            'customTableStyles': {},
            'globalFilters': self.global_filters,
            'lists': self.lists,
            'listNextId': len(self.lists) + 1,
            'chartOdooMenusReferences': self.link_references,
        }

    def to_odoo_18_json(self):
        """ The workbook as the spreadsheet library of Odoo 18.0 reads it """
        return to_odoo_18(self.to_json())

    def dump(self, path):
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(self.to_odoo_18_json(), file, indent=4, ensure_ascii=False)
            file.write('\n')


def _odoo_18_figure(figure):
    """ A figure of 19.0 as 18.0 stores it: placed by x and y, a chart without its id, a carousel of one Odoo
    chart as that chart. """
    offset = figure.pop('offset', {})
    figure.pop('col', None)
    figure.pop('row', None)
    figure = {'id': figure['id'], 'x': offset.get('x', 0), 'y': offset.get('y', 0), **figure}
    data = figure['data']
    if figure['tag'] == 'carousel':
        # 18.0 has no carousel: the Odoo chart is the figure, with the title and the filters of the carousel
        (chart_id, definition), = data['chartDefinitions'].items()
        definition = dict(definition)
        definition.pop('actionXmlId', None)
        definition['title'] = data.get('title') or definition.get('title') or {}
        definition['fieldMatching'] = data.get('fieldMatching', {}).get(chart_id, {})
        figure['tag'] = 'chart'
        figure['data'] = data = definition
    if figure['tag'] == 'chart':
        data.pop('chartId', None)
        data.pop('cumulatedStart', None)
        if data.get('type') == 'scorecard' and isinstance(data.get('baselineDescr'), dict):
            data['baselineDescr'] = data['baselineDescr'].get('text', '')
    return figure


def _odoo_18_filter(global_filter):
    if global_filter['type'] == 'date':
        default = global_filter.get('defaultValue')
        global_filter['rangeType'] = 'relative'
        if default:
            global_filter['defaultValue'] = ODOO_18_DATE_DEFAULTS.get(default, default)
    elif global_filter['type'] == 'text':
        ranges = global_filter.pop('rangesOfAllowedValues', None)
        if ranges:
            global_filter['rangeOfAllowedValues'] = ranges[0]
        default = global_filter.get('defaultValue')
        if isinstance(default, dict):
            strings = default.get('strings') or []
            global_filter['defaultValue'] = strings[0] if strings else ''
    elif global_filter['type'] == 'relation':
        default = global_filter.get('defaultValue')
        if isinstance(default, dict):
            global_filter['includeChildren'] = default.get('operator') == 'child_of'
            global_filter['defaultValue'] = default.get('ids') or []
        global_filter.setdefault('defaultValue', [])
    return global_filter


def to_odoo_18(data):
    """ The workbook of 19.0 in the format of the spreadsheet library of Odoo 18.0: the migration steps of 19.0
    after 18.0.4 (the version 22) undone, and those of the Odoo data after the version 12. """
    data['version'] = ODOO_18_VERSION
    data['odooVersion'] = ODOO_18_ODOO_VERSION
    for sheet in data['sheets']:
        # 18.1.1: a cell was an object
        sheet['cells'] = {xc: {'content': content} for xc, content in sheet['cells'].items()}
        # 18.3.1, 18.4.2, 18.5.1 and the carousels of 19.0
        sheet['figures'] = [_odoo_18_figure(figure) for figure in sheet['figures']]
    for pivot in data['pivots'].values():
        # 18.4.3 and the Odoo data 12 to 13: the sorted column names its measure by field
        sorted_column = pivot.get('sortedColumn')
        if sorted_column:
            measure = next(m for m in pivot['measures'] if m['id'] == sorted_column['measure'])
            pivot['sortedColumn'] = {
                'groupId': [[], []], 'measure': measure['fieldName'], 'order': sorted_column['order'],
            }
    # the global filters of the Odoo data 18.4.10 to 18.5.10
    data['globalFilters'] = [_odoo_18_filter(global_filter) for global_filter in data['globalFilters']]
    return data


# -- helpers shared by the dashboards -------------------------------------------------

def dashboard_sheet(workbook):
    sheet = workbook.sheet('Dashboard', cols=20, rows=80)
    sheet.background = BACKGROUND
    return sheet


def first_month_cells(data, row):
    """ The first month of the Period filter, or of the last twelve months without a period
    :return: the absolute reference of the first month """
    data.set(0, row, label('Period start'), TEXT)
    data.set(1, row, '=ODOO.FILTER.VALUE("Period")', fmt='mm/dd/yyyy')
    data.set(0, row + 1, label('First month'), TEXT)
    data.set(1, row + 1, '=IF(ISNUMBER(B{r}),DATE(YEAR(B{r}),MONTH(B{r}),1),'
                         'EDATE(DATE(YEAR(TODAY()),MONTH(TODAY()),1),-11))'.format(r=row + 1), fmt='mm/dd/yyyy')
    return '$B$%s' % (row + 2)


def cards(dashboard, items, width, y=0, per_row=4):
    """ :param items: (key, title, value, baseline, baseline text, colour up, colour down) """
    figures = {}
    for index, (key, title, value, baseline, text, up, down) in enumerate(items):
        x = (index % per_row) * (width + 10)
        figures[key] = dashboard.scorecard(key, title, value, x, y + (index // per_row) * 120, width, 110,
                                           baseline=baseline, baseline_text=text,
                                           baseline_mode='text' if text else 'percentage')
        dashboard.figures[-1]['data'].update(baselineColorUp=up, baselineColorDown=down)
    return figures


# -- styles used by all the dashboards ---------------------------------------------

HEADER = {'textColor': GREY, 'bold': True, 'fontSize': 11, 'fillColor': '#E7F2F2'}
HEADER_RIGHT = {**HEADER, 'align': 'right'}
TEXT = {'textColor': GREY}
TOTAL = {'textColor': GREY, 'bold': True}
TOTAL_FILL = {'textColor': TEAL, 'bold': True, 'fillColor': '#F1F7F7'}
NOTE = {'textColor': '#8F8F8F', 'italic': True}
LINE_BOTTOM = {'bottom': {'style': 'thin', 'color': '#D9D9D9'}}
LINE_TOP = {'top': {'style': 'thin', 'color': TEAL}}
