"""Excel file of an inventory report: real numbers and dates, the groups as
Excel outline levels (they fold in Excel too), frozen header and first column,
filters on the header, and the report filters on the first rows."""
import csv
import io

import xlsxwriter

NUMERIC = ('float', 'monetary', 'int', 'percent', 'days', 'ratio')
# shades of the group rows, from the top level down
GROUP_FILLS = ('#E8E1EC', '#F1ECF4', '#F7F4F9', '#FBFAFC')


def build_xlsx(exporter, export):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_numbers': False})
    sheet = workbook.add_worksheet((export['title'] or 'Report')[:31])
    currency = export['currency']
    digits = export['digits']
    qty_format = '#,##0.%s' % ('0' * digits) if digits else '#,##0'
    if currency.position == 'before':
        money_format = '"%s" #,##0.00' % currency.symbol
    else:
        money_format = '#,##0.00 "%s"' % currency.symbol

    base = {'font_size': 10, 'valign': 'vcenter'}
    formats = {}

    def fmt(kind, style='line', level=0):
        key = (kind, style, level)
        if key not in formats:
            props = dict(base)
            props['num_format'] = {
                'float': qty_format, 'monetary': money_format, 'int': '#,##0', 'percent': '0.0" %"', 'ratio': '0.00',
                'days': '#,##0', 'datetime': 'yyyy-mm-dd hh:mm', 'date': 'yyyy-mm-dd',
            }.get(kind, '@')
            if style == 'group':
                props.update(bold=True, bg_color=GROUP_FILLS[min(level, len(GROUP_FILLS) - 1)])
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
    header = workbook.add_format({'bold': True, 'font_size': 10, 'bg_color': '#3E2D4F', 'font_color': '#FFFFFF',
                                  'border': 0, 'valign': 'vcenter', 'text_wrap': True})
    header_num = workbook.add_format({'bold': True, 'font_size': 10, 'bg_color': '#3E2D4F', 'font_color': '#FFFFFF',
                                      'align': 'right', 'valign': 'vcenter', 'text_wrap': True})

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

    header_row = row
    sheet.set_row(header_row, 30)
    sheet.write(header_row, 0, export['group_label'], header)
    for index, column in enumerate(columns, start=1):
        numeric = column['type'] in NUMERIC
        sheet.write(header_row, index, column['label'], header_num if numeric else header)
    row += 1

    widths = [max(len(export['group_label']), 30)] + [max(len(c['label']) + 2, 12) for c in columns]

    def write_line(line, style):
        nonlocal row
        level = line.get('level', 0)
        line_style = style or ('group' if line['kind'] == 'group' or (line['kind'] == 'leaf' and line.get('has_children'))
                               else line['kind'] if line['kind'] in ('opening', 'closing') else 'line')
        sheet.write(row, 0, line['name'] or '', fmt('name', line_style, level))
        widths[0] = max(widths[0], min(len(line['name'] or '') + 2 * level + 2, 70))
        for index, column in enumerate(columns, start=1):
            cell_format = fmt(column['type'], line_style, level)
            if column.get('detail_only') and line['kind'] != 'detail':
                sheet.write_blank(row, index, None, cell_format)
                continue
            value = (line.get('values') or {}).get(column['key'])
            if value in (None, False, ''):
                sheet.write_blank(row, index, None, cell_format)
            elif column['type'] in NUMERIC:
                sheet.write_number(row, index, value, cell_format)
            elif column['type'] == 'datetime':
                sheet.write_datetime(row, index, exporter._om_local_datetime(value), cell_format)
                widths[index] = max(widths[index], 17)
            elif column['type'] == 'date':
                sheet.write_datetime(row, index, value, cell_format)
            else:
                sheet.write_string(row, index, str(value), cell_format)
                widths[index] = max(widths[index], min(len(str(value)) + 2, 50))
        if style != 'total':
            sheet.set_row(row, None, None, {'level': min(level, 7)})
        row += 1

    for line in export['lines']:
        write_line(line, None)
    write_line(export['total'], 'total')

    for index, width in enumerate(widths):
        sheet.set_column(index, index, width)
    sheet.freeze_panes(header_row + 1, 1)
    sheet.autofilter(header_row, 0, row - 2, len(columns))
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
    writer.writerow([export['group_label'], 'Level'] + [c['label'] for c in columns])
    for line in export['lines'] + [export['total']]:
        values = line.get('values') or {}
        cells = []
        for column in columns:
            value = values.get(column['key'])
            if column.get('detail_only') and line['kind'] != 'detail':
                value = ''
            elif column['type'] == 'datetime' and value:
                value = exporter._om_local_datetime(value).strftime('%Y-%m-%d %H:%M')
            cells.append('' if value in (None, False) else value)
        writer.writerow([line['name'], line.get('level', 0)] + cells)
    return output.getvalue().encode('utf-8-sig')
