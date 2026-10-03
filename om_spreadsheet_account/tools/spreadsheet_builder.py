""" Build the JSON of an Odoo spreadsheet dashboard from Python.

The dashboards of the Dashboards app are o-spreadsheet workbooks stored as JSON. Community Odoo cannot edit them,
so they are written here in code: cells, pivots, lists, charts and global filters, then dumped next to the module.
The dashboards are written in the format of the spreadsheet library of Odoo 19.0 (version 18.5.10), then brought
back to the one of Odoo 16.0 by `to_odoo_16` (version 12, Odoo data version 5).

Not loaded by Odoo: run the build script of the module to regenerate the files.
"""
import json
import re
import uuid

VERSION = '18.5.10'
# the data versions of the spreadsheet library of Odoo 16.0
ODOO_16_VERSION = 12
ODOO_16_ODOO_VERSION = 5

# the relative date filters of 19.0 as Odoo 16.0 has them: a range type and whether the current period is the default
ODOO_16_DATE_DEFAULTS = {
    'this_year': ('year', True),
    'year_to_date': ('year', True),
    'this_quarter': ('quarter', True),
    'this_month': ('month', True),
    'last_7_days': ('relative', 'last_week'),
    'last_30_days': ('relative', 'last_month'),
    'last_90_days': ('relative', 'last_three_months'),
    'last_12_months': ('relative', 'last_year'),
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

    def to_odoo_16_json(self):
        """ The workbook as the spreadsheet library of Odoo 16.0 reads it """
        return to_odoo_16(self.to_json())

    def dump(self, path):
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(self.to_odoo_16_json(), file, indent=4, ensure_ascii=False)
            file.write('\n')


def _a1_to_cell(a1):
    """ 'E32' -> (column index, row index) """
    letters = ''.join(char for char in a1 if char.isalpha())
    digits = a1[len(letters):]
    col = 0
    for char in letters:
        col = col * 26 + ord(char.upper()) - 64
    return col - 1, int(digits) - 1


def _range_cells(data_range):
    """ 'Data!E32:E43' -> ('Data', [(col, row), ...]) in the order of the range, by column or by row """
    sheet_name, _sep, zone = data_range.rpartition('!')
    first, _sep, last = zone.replace('$', '').partition(':')
    first_col, first_row = _a1_to_cell(first)
    last_col, last_row = _a1_to_cell(last or first)
    cells = [(col, row) for col in range(first_col, last_col + 1) for row in range(first_row, last_row + 1)]
    return sheet_name, cells


def _with_title_cell(data_range):
    """ The range with the cell 16.0 reads its title from: above a column, on the left of a row
    :return: (range, sheet name, title cell) """
    sheet_name, cells = _range_cells(data_range)
    (first_col, first_row), (last_col, last_row) = cells[0], cells[-1]
    if first_col == last_col:
        title_col, title_row = first_col, first_row - 1
    else:
        title_col, title_row = first_col - 1, first_row
    title = cell_ref(title_col, title_row)
    return '%s!%s:%s' % (sheet_name, title, cell_ref(last_col, last_row)), sheet_name.strip("'"), title


def _titled_copy(data_set, sheets_by_name):
    """ A new column, on the Data sheet if there is one: the label of the data set, then the cells of the range
    :return: the range of the copy, with its title """
    sheet_name, cells = _range_cells(data_set['dataRange'])
    source_name = sheet_name.strip("'")
    sheet = sheets_by_name.get('Data') or sheets_by_name[source_name]
    prefix = '' if sheet['name'] == source_name else '%s!' % sheet_name
    col = sheet['colNumber']
    sheet['colNumber'] += 1
    if sheet['name'] == source_name:
        sheet['cols'].setdefault(str(col), {})['isHidden'] = True
    sheet['cells'][cell_ref(col, 0)] = {'content': label(data_set.get('label') or '')}
    for offset, (source_col, source_row) in enumerate(cells):
        sheet['cells'][cell_ref(col, offset + 1)] = {
            'content': '=%s%s' % (prefix, cell_ref(source_col, source_row))}
    target = "'%s'" % sheet['name'] if not sheet['name'].isalnum() else sheet['name']
    return '%s!%s:%s' % (target, cell_ref(col, 0), cell_ref(col, len(cells)))


def _odoo_16_title(title):
    return title.get('text', '') if isinstance(title, dict) else (title or '')


def _odoo_16_figure(figure, sheets_by_name):
    """ A figure of 19.0 as 16.0 stores it: placed by x and y, the title a text, a carousel of one Odoo chart as
    that chart, a combo chart as a bar chart, the label of a data set in the cell above its range. """
    offset = figure.pop('offset', {})
    figure.pop('col', None)
    figure.pop('row', None)
    figure = {'id': figure['id'], 'x': offset.get('x', 0), 'y': offset.get('y', 0), **figure}
    data = figure['data']
    if figure['tag'] == 'carousel':
        (chart_id, definition), = data['chartDefinitions'].items()
        definition = dict(definition)
        definition.pop('actionXmlId', None)
        definition['title'] = data.get('title') or definition.get('title') or {}
        definition['fieldMatching'] = data.get('fieldMatching', {}).get(chart_id, {})
        figure['tag'] = 'chart'
        figure['data'] = data = definition
    for key in ('chartId', 'cumulatedStart', 'humanize', 'aggregated'):
        data.pop(key, None)
    data['title'] = _odoo_16_title(data.get('title'))
    chart_type = data.get('type')
    if chart_type.startswith('odoo_'):
        data['metaData'].pop('mode', None)
        data.pop('dataSets', None)
        data.setdefault('background', '#FFFFFF')
        data.setdefault('verticalAxisPosition', 'left')
    elif chart_type == 'scorecard':
        if isinstance(data.get('baselineDescr'), dict):
            data['baselineDescr'] = data['baselineDescr'].get('text', '')
    elif chart_type == 'gauge':
        rule = data.get('sectionRule') or {}
        for point in ('lowerInflectionPoint', 'upperInflectionPoint'):
            if point in rule:
                rule[point].pop('operator', None)
    elif chart_type in ('bar', 'line', 'combo', 'pie'):
        if chart_type == 'combo':
            # 16.0 has no combo chart
            data['type'] = 'bar'
        data_sets = []
        with_titles = True
        for data_set in data['dataSets']:
            data_range, sheet_name, title_cell = _with_title_cell(data_set['dataRange'])
            sheet = sheets_by_name.get(sheet_name)
            current = sheet and sheet['cells'].get(title_cell, {}).get('content')
            if sheet is None or (current and current != label(data_set.get('label') or '')):
                with_titles = False
                break
            data_sets.append((data_range, sheet, title_cell, data_set.get('label') or ''))
        if with_titles:
            for data_range, sheet, title_cell, text in data_sets:
                sheet['cells'].setdefault(title_cell, {})['content'] = label(text)
            data['dataSets'] = [data_range for data_range, _sheet, _cell, _text in data_sets]
        else:
            # no free cell above the ranges for their labels: a copy of each range under its label, in new columns
            data['dataSets'] = [_titled_copy(data_set, sheets_by_name) for data_set in data['dataSets']]
        data['dataSetsHaveTitle'] = True
        data.setdefault('background', '#FFFFFF')
        data.setdefault('verticalAxisPosition', 'left')
    return figure


def _odoo_16_filter(global_filter):
    if global_filter['type'] == 'date':
        default = global_filter.pop('defaultValue', None)
        range_type, value = ODOO_16_DATE_DEFAULTS.get(default, ('year', bool(default)))
        global_filter['rangeType'] = range_type
        if range_type == 'relative':
            global_filter['defaultValue'] = value
            global_filter['defaultsToCurrentPeriod'] = False
        else:
            global_filter['defaultValue'] = {}
            global_filter['defaultsToCurrentPeriod'] = value
    elif global_filter['type'] == 'text':
        # a text typed by the user: 16.0 has no list of values to pick from
        global_filter.pop('rangesOfAllowedValues', None)
        default = global_filter.get('defaultValue')
        if isinstance(default, dict):
            strings = default.get('strings') or []
            global_filter['defaultValue'] = strings[0] if strings else ''
        global_filter.setdefault('defaultValue', '')
    elif global_filter['type'] == 'relation':
        default = global_filter.get('defaultValue')
        global_filter['defaultValue'] = default.get('ids') or [] if isinstance(default, dict) else (default or [])
        global_filter.pop('domainOfAllowedValues', None)
        global_filter.setdefault('defaultValueDisplayNames', [])
    return global_filter


def _odoo_16_pivot(pivot):
    """ A pivot of 19.0 as 16.0 stores it: the group bys as `field:granularity`, the measures by field """

    def group_by(dimension):
        if dimension.get('granularity'):
            return '%s:%s' % (dimension['fieldName'], dimension['granularity'])
        return dimension['fieldName']

    converted = {
        'id': pivot['id'],
        'name': pivot['name'],
        'model': pivot['model'],
        'domain': pivot['domain'],
        'context': pivot.get('context') or {},
        'measures': [{'field': measure['fieldName']} for measure in pivot['measures']],
        'rowGroupBys': [group_by(row) for row in pivot['rows']],
        'colGroupBys': [group_by(column) for column in pivot['columns']],
        'fieldMatching': pivot.get('fieldMatching', {}),
    }
    sorted_column = pivot.get('sortedColumn')
    if sorted_column:
        measure = next(m for m in pivot['measures'] if m['id'] == sorted_column['measure'])
        converted['sortedColumn'] = {
            'groupId': [[], []], 'measure': measure['fieldName'], 'order': sorted_column['order'],
        }
    return converted


PIVOT_TABLE = re.compile(r'^=PIVOT\((\d+)(?:,(\d+))?(?:,(TRUE|FALSE))?(?:,(TRUE|FALSE))?\)$', re.IGNORECASE)
PIVOT_FUNCTION = re.compile(r'\bPIVOT\.(VALUE|HEADER)\(')
FILTER_VALUE = re.compile(r'^=ODOO\.FILTER\.VALUE\("([^"]+)"\)$')


def _odoo_16_measure_formulas(content, pivots):
    """ PIVOT.VALUE and PIVOT.HEADER of 19.0 are ODOO.PIVOT and ODOO.PIVOT.HEADER, the measures named by field """
    content = PIVOT_FUNCTION.sub(lambda match: 'ODOO.PIVOT(' if match.group(1) == 'VALUE' else 'ODOO.PIVOT.HEADER(',
                                 content)
    for pivot in pivots.values():
        for measure in pivot['measures']:
            if measure['id'] != measure['fieldName']:
                content = content.replace('"%s"' % measure['id'], '"%s"' % measure['fieldName'])
    return content


def _expand_pivot_table(sheet, xc, match, pivot):
    """ The dynamic PIVOT() table of 19.0 as the formulas of 16.0: a header row if asked, the total, then the rows
    by position """
    pivot_id, row_count = match.group(1), int(match.group(2) or 10)
    with_total = (match.group(3) or 'TRUE').upper() == 'TRUE'
    with_titles = (match.group(4) or 'TRUE').upper() == 'TRUE'
    col, row = _a1_to_cell(xc)
    measures = [measure['fieldName'] for measure in pivot['measures']]
    row_field = pivot['rows'][0]['fieldName'] if pivot['rows'] else None
    cells = sheet['cells']
    del cells[xc]
    if with_titles:
        for index, measure in enumerate(measures):
            cells[cell_ref(col + 1 + index, row)] = {
                'content': '=ODOO.PIVOT.HEADER(%s,"measure","%s")' % (pivot_id, measure)}
        row += 1
    if with_total:
        cells[cell_ref(col, row)] = {'content': label('Total')}
        for index, measure in enumerate(measures):
            cells[cell_ref(col + 1 + index, row)] = {'content': '=ODOO.PIVOT(%s,"%s")' % (pivot_id, measure)}
        row += 1
    if not row_field:
        return
    for position in range(1, row_count + 1):
        cells[cell_ref(col, row)] = {
            'content': '=ODOO.PIVOT.HEADER(%s,"#%s",%s)' % (pivot_id, row_field, position)}
        for index, measure in enumerate(measures):
            cells[cell_ref(col + 1 + index, row)] = {
                'content': '=ODOO.PIVOT(%s,"%s","#%s",%s)' % (pivot_id, measure, row_field, position)}
        row += 1


TEXT_FUNCTIONS = ('_t(', 'TEXT(', 'CONCATENATE(', 'ODOO.LIST', 'PIVOT.HEADER(', 'FILTER.VALUE(', 'OM.FILTER.')


def _default_number_formats(sheets, formats):
    """ The number formulas of the dashboards without a format: 19.0 takes the one of the cells they read, 16.0
    shows them unformatted. The amounts get two decimals, the counts none. """
    amount, count = '#,##0.00', '#,##0'
    for fmt in (amount, count):
        if fmt not in formats.values():
            formats[str(len(formats) + 1)] = fmt
    format_ids = {fmt: key for key, fmt in formats.items()}
    for sheet in sheets:
        if sheet['name'] != 'Dashboard':
            continue
        for cell in sheet['cells'].values():
            content = cell.get('content') or ''
            if not content.startswith('=') or 'format' in cell or any(f in content for f in TEXT_FUNCTIONS):
                continue
            cell['format'] = format_ids[count if '"__count"' in content else amount]


def to_odoo_16(data):
    """ The workbook of 19.0 in the format of the spreadsheet library of Odoo 16.0 (version 12, Odoo data 5) """
    styles = data['styles']
    formats = data['formats']
    borders = {
        key: {side: [value['style'], value['color']] for side, value in border.items()}
        for key, border in data['borders'].items()
    }
    sheets = []
    for sheet in data['sheets']:
        cells = {}
        for xc, content in sheet['cells'].items():
            cells[xc] = {'content': content}
        for attribute, values in (('style', sheet['styles']), ('format', sheet['formats']),
                                  ('border', sheet['borders'])):
            for xc, key in values.items():
                cells.setdefault(xc, {})[attribute] = key
        sheets.append({
            'id': sheet['id'],
            'name': sheet['name'],
            'colNumber': sheet['colNumber'],
            'rowNumber': sheet['rowNumber'],
            'rows': sheet['rows'],
            'cols': sheet['cols'],
            'merges': sheet['merges'],
            'cells': cells,
            'conditionalFormats': sheet['conditionalFormats'],
            'figures': sheet['figures'],
            'areGridLinesVisible': sheet['areGridLinesVisible'],
            'isVisible': sheet['isVisible'],
        })
    _default_number_formats(sheets, formats)
    sheets_by_name = {sheet['name']: sheet for sheet in sheets}
    for sheet in sheets:
        cells = sheet['cells']
        for xc in list(cells):
            content = cells[xc].get('content') or ''
            match = PIVOT_TABLE.match(content)
            if match:
                _expand_pivot_table(sheet, xc, match, data['pivots'][match.group(1)])
                continue
            match = FILTER_VALUE.match(content)
            if match and any(f['label'] == match.group(1) and f['type'] == 'date' for f in data['globalFilters']):
                # the dates of a date filter: 19.0 spills them on two cells, 16.0 gives its text only
                col, row = _a1_to_cell(xc)
                cells[xc]['content'] = '=OM.FILTER.START("%s")' % match.group(1)
                cells.setdefault(cell_ref(col + 1, row), {})['content'] = '=OM.FILTER.END("%s")' % match.group(1)
                continue
            if 'PIVOT.' in content:
                cells[xc]['content'] = _odoo_16_measure_formulas(content, data['pivots'])
        sheet['figures'] = [_odoo_16_figure(figure, sheets_by_name) for figure in sheet['figures']]
    return {
        'version': ODOO_16_VERSION,
        'odooVersion': ODOO_16_ODOO_VERSION,
        'sheets': sheets,
        'styles': styles,
        'formats': formats,
        'borders': borders,
        'revisionId': data['revisionId'],
        'chartOdooMenusReferences': data['chartOdooMenusReferences'],
        'pivots': {pivot_id: _odoo_16_pivot(pivot) for pivot_id, pivot in data['pivots'].items()},
        'pivotNextId': data['pivotNextId'],
        'lists': data['lists'],
        'listNextId': data['listNextId'],
        'globalFilters': [_odoo_16_filter(global_filter) for global_filter in data['globalFilters']],
    }


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
