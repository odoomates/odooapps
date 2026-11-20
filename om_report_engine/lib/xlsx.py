"""Excel and CSV files of a dynamic report: real numbers and dates, the groups
as Excel outline levels (they fold in Excel too), the column groups as a
merged header row, frozen header and first column, filters on the header,
and what the report was run with on the first rows."""
import csv
import io

import xlsxwriter

from odoo import fields

NUMERIC = ('monetary', 'float', 'int', 'percent', 'ratio', 'days')
# shades of the group rows, from the top level down
GROUP_FILLS = ('#E8E1EC', '#F1ECF4', '#F7F4F9', '#FBFAFC')
DETAIL_KINDS = ('detail', 'opening', 'closing')


def _hidden(column, line):
    return column.get('detail_only') and line.get('kind') not in DETAIL_KINDS


def build_xlsx(exporter, export):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_numbers': False})
    sheet = workbook.add_worksheet((export['title'] or 'Report')[:31])
    if exporter.env['res.lang']._lang_get(exporter.env.lang or 'en_US').direction == 'rtl':
        sheet.right_to_left()
    currency = export['currency']
    rounding = export.get('rounding')
    decimals = '' if rounding else '0' * (currency.decimal_places or 0)
    amount = '#,##0.%s' % decimals if decimals else '#,##0'
    if rounding and rounding['suffix']:
        amount = '%s" %s"' % (amount, rounding['suffix'])
    if currency.position == 'before':
        money_format = '"%s" %s;-"%s" %s' % (currency.symbol, amount, currency.symbol, amount)
    else:
        money_format = '%s "%s";-%s "%s"' % (amount, currency.symbol, amount, currency.symbol)

    base = {'font_size': 10, 'valign': 'vcenter'}
    formats = {}

    def fmt(kind, style='line', level=0, digits=2):
        key = (kind, style, level, digits)
        if key not in formats:
            props = dict(base)
            props['num_format'] = {
                'monetary': money_format, 'float': '#,##0.%s' % ('0' * digits) if digits else '#,##0',
                'int': '#,##0', 'percent': '0.0" %"', 'ratio': '0.00',
                'days': '0.%s" d"' % ('0' * digits) if digits else '0" d"',
                'datetime': 'yyyy-mm-dd hh:mm', 'date': 'yyyy-mm-dd',
            }.get(kind, '@')
            if style == 'group':
                props.update(bold=True, bg_color=GROUP_FILLS[min(level, len(GROUP_FILLS) - 1)])
            elif style == 'section':
                props.update(bold=True)
            elif style == 'total':
                props.update(bold=True, top=2, bg_color='#E8E1EC')
            elif style in ('opening', 'closing'):
                props.update(italic=True, font_color='#666666')
            if kind == 'name':
                props['indent'] = min(level, 15)
            formats[key] = workbook.add_format(props)
        return formats[key]

    title = workbook.add_format({'bold': True, 'font_size': 15, 'font_color': '#3E2D4F'})
    label = workbook.add_format({'bold': True, 'font_size': 10, 'font_color': '#555555'})
    text = workbook.add_format({'font_size': 10})
    header_props = {'bold': True, 'font_size': 10, 'bg_color': '#3E2D4F', 'font_color': '#FFFFFF',
                    'valign': 'vcenter', 'text_wrap': True}
    header = workbook.add_format(header_props)
    header_num = workbook.add_format({**header_props, 'align': 'right'})
    header_group = workbook.add_format({**header_props, 'align': 'center', 'bottom': 1, 'bottom_color': '#FFFFFF'})

    columns = export['columns']
    row = 0
    sheet.write(row, 0, export['title'], title)
    sheet.write(row, 2, export['company'].name, text)
    row += 1
    for name, value in export['filters']:
        sheet.write(row, 0, name, label)
        sheet.write(row, 1, value, text)
        row += 1
    row += 1

    groups = exporter._om_header_groups(columns)
    if groups:
        sheet.write(row, 0, '', header_group)
        index = 1
        for group_label, span in groups:
            if span > 1:
                sheet.merge_range(row, index, row, index + span - 1, group_label, header_group)
            else:
                sheet.write(row, index, group_label, header_group)
            index += span
        row += 1
    header_row = row
    sheet.set_row(header_row, 30)
    sheet.write(header_row, 0, export['name_label'] or '', header)
    for index, column in enumerate(columns, start=1):
        sheet.write(header_row, index, column['label'], header_num if column['type'] in NUMERIC else header)
    row += 1

    widths = [max(len(export['name_label'] or ''), 30)] + [max(len(c['label']) + 2, 12) for c in columns]

    def write_line(line, style):
        nonlocal row
        level = line.get('level', 0)
        kind = line['kind']
        line_style = style or (
            'group' if kind == 'group' or (kind == 'leaf' and line.get('has_children'))
            else kind if kind in ('opening', 'closing', 'section') else 'line')
        sheet.write(row, 0, line['name'] or '', fmt('name', line_style, level))
        widths[0] = max(widths[0], min(len(line['name'] or '') + 2 * level + 2, 70))
        for index, column in enumerate(columns, start=1):
            cell_type = (line.get('types') or {}).get(column['key']) or column['type']
            cell_format = fmt(cell_type, line_style, level, column.get('digits', 1 if cell_type == 'days' else 2))
            value = (line.get('values') or {}).get(column['key'])
            if column.get('blank_zero') and value == 0 and kind == 'detail':
                value = None
            notes = (line.get('notes') or {}).get(column['key'])
            if notes:
                sheet.write_comment(row, index, '\n\n'.join('%s: %s' % (n['author'], n['note']) for n in notes),
                                    {'x_scale': 2, 'y_scale': 1.5})
            if _hidden(column, line) or value in (None, False, ''):
                sheet.write_blank(row, index, None, cell_format)
            elif cell_type in NUMERIC:
                if cell_type == 'monetary' and rounding:
                    value = round(value / rounding['factor'])
                sheet.write_number(row, index, value, cell_format)
            elif column['type'] == 'datetime':
                sheet.write_datetime(row, index, exporter._om_local_datetime(value), cell_format)
                widths[index] = max(widths[index], 17)
            elif column['type'] == 'date':
                sheet.write_datetime(row, index, fields.Date.to_date(value), cell_format)
            else:
                sheet.write_string(row, index, str(value), cell_format)
                widths[index] = max(widths[index], min(len(str(value)) + 2, 50))
        if style != 'total':
            sheet.set_row(row, None, None, {'level': min(level, 7)})
        row += 1

    for line in export['lines']:
        write_line(line, None)
    if export['total']:
        write_line(export['total'], 'total')

    for index, width in enumerate(widths):
        sheet.set_column(index, index, width)
    sheet.freeze_panes(header_row + 1, 1)
    if export['lines']:
        sheet.autofilter(header_row, 0, header_row + len(export['lines']), len(columns))
    sheet.outline_settings(True, False, True, False)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(header_row)
    workbook.close()
    return output.getvalue()


def build_csv(exporter, export):
    output = io.StringIO()
    writer = csv.writer(output)
    columns = export['columns']
    writer.writerow([export['name_label'] or '', 'Level']
                    + ['%s %s' % (c['group'], c['label']) if c.get('group') else c['label'] for c in columns])
    lines = export['lines'] + ([export['total']] if export['total'] else [])
    for line in lines:
        values = line.get('values') or {}
        cells = []
        for column in columns:
            value = values.get(column['key'])
            if _hidden(column, line):
                value = ''
            elif column['type'] == 'datetime' and value:
                value = exporter._om_local_datetime(value).strftime('%Y-%m-%d %H:%M')
            cells.append('' if value in (None, False) else value)
        writer.writerow([line['name'], line.get('level', 0)] + cells)
    return output.getvalue().encode('utf-8-sig')
