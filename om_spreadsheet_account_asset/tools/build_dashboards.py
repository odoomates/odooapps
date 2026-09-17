#!/usr/bin/env python3
""" Write the Assets dashboard of om_spreadsheet_account_asset into data/files.

    python3 om_spreadsheet_account_asset/tools/build_dashboards.py

It reads the assets and the depreciation analysis of om_account_asset.
The builder is the one of om_spreadsheet_account.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'om_spreadsheet_account', 'tools'))

from spreadsheet_builder import (  # noqa: E402
    GREEN, HEADER, HEADER_RIGHT, INTEGER_FORMAT, RED, TEXT, Workbook, cards, dashboard_sheet, first_month_cells,
    label,
)

FILES = os.path.join(os.path.dirname(HERE), 'data', 'files')

MONTH_FORMAT = 'mmm yyyy'


def build_assets():
    workbook = Workbook('assets')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    period = workbook.date_filter('period', 'Period', 'this_year')
    category = workbook.relation_filter('category', 'Asset Category', 'account.asset.category',
                                        domain=[['type', '=', 'purchase']])
    running = [['state', 'in', ['open', 'paused']], ['category_id.type', '=', 'purchase']]
    assets = workbook.pivot('Assets by Category', 'account.asset.asset', running,
                            ['value', 'opening_depreciation', '__count'], rows=['category_id'],
                            field_matching={category: ('category_id', 'many2one')},
                            sorted_column=('value', 'desc'))
    posted = workbook.pivot(
        'Posted Depreciation', 'asset.asset.report',
        [['move_check', '=', True], ['state', 'in', ['open', 'paused']],
         ['asset_category_id.type', '=', 'purchase']],
        ['posted_value'], field_matching={category: ('asset_category_id', 'many2one')})
    board = workbook.pivot(
        'Depreciation by Month', 'asset.asset.report', [['asset_category_id.type', '=', 'purchase']],
        ['posted_value', 'unposted_value'], rows=[('depreciation_date', 'month')],
        field_matching={period: ('depreciation_date', 'date'), category: ('asset_category_id', 'many2one')})

    figures = [
        ('gross', 'Gross value of the running assets', '=PIVOT.VALUE(%s,"value")' % assets, None),
        ('opening', 'Opening depreciation', '=PIVOT.VALUE(%s,"opening_depreciation")' % assets, None),
        ('posted', 'Depreciation posted', '=PIVOT.VALUE(%s,"posted_value")' % posted, None),
        ('accumulated', 'Accumulated depreciation', '=B2+B3', None),
        ('book', 'Book value', '=B1-B4', None),
        ('count', 'Running assets', '=PIVOT.VALUE(%s,"__count")' % assets, INTEGER_FORMAT),
        ('period_posted', 'Depreciation posted in the period', '=PIVOT.VALUE(%s,"posted_value")' % board, None),
        ('period_planned', 'Depreciation to post in the period', '=PIVOT.VALUE(%s,"unposted_value")' % board,
         None),
    ]
    refs = {}
    for row, (key, text, formula, fmt) in enumerate(figures):
        data.set(0, row, label(text), TEXT)
        refs[key] = data.set(1, row, formula, fmt=fmt)
    first = first_month_cells(data, 9)
    data.set(3, 0, label('Month'), HEADER)
    data.set(4, 0, label('Posted'), HEADER_RIGHT)
    data.set(5, 0, label('To Post'), HEADER_RIGHT)
    for index in range(12):
        row = 1 + index
        data.set(3, row, '=EDATE(%s,%s)' % (first, index), fmt=MONTH_FORMAT)
        month = 'TEXT(D%s,"mm/yyyy")' % (row + 1)
        data.set(4, row, '=PIVOT.VALUE(%s,"posted_value","depreciation_date:month",%s)' % (board, month))
        data.set(5, row, '=PIVOT.VALUE(%s,"unposted_value","depreciation_date:month",%s)' % (board, month))
    data.col_sizes.update({0: 260, 3: 110})

    width = 317
    items = [
        ('gross', 'Gross Value', refs['gross'], None, None, GREEN, RED),
        ('accumulated', 'Accumulated Depreciation', refs['accumulated'], None, None, GREEN, RED),
        ('book', 'Book Value', refs['book'], None, None, GREEN, RED),
        ('count', 'Running Assets', refs['count'], None, None, GREEN, RED),
        ('period_posted', 'Depreciation Posted', refs['period_posted'], None, None, GREEN, RED),
        ('period_planned', 'Depreciation to Post', refs['period_planned'], None, None, GREEN, RED),
    ]
    figures = cards(dashboard, items, width, per_row=3)
    for key in ('gross', 'book', 'count'):
        workbook.link_menu(figures[key], 'om_account_asset.menu_action_account_asset_asset_form')
    workbook.link_menu(figures['period_planned'], 'om_account_asset.menu_asset_depreciation_schedule')
    dashboard.chart(
        'monthly', 'bar', 'Depreciation by Month', data.range(3, 1, 3, 12),
        [(data.range(4, 1, 4, 12), 'Posted', None), (data.range(5, 1, 5, 12), 'To Post', None)],
        0, 240, 590, 340, stacked=True)
    dashboard.odoo_chart(
        'by_category', 'pie', 'By Category', 'account.asset.asset', 'value', ['category_id'],
        running, 600, 240, 370, 340, field_matching={category: ('category_id', 'many2one')},
        action_xmlid='om_account_asset.action_account_asset_asset_form')
    top = 26
    dashboard.set(0, top, label('Running Assets by Category'), HEADER)
    for col in (1, 2, 3):
        dashboard.set(col, top, None, HEADER)
    dashboard.set(0, top + 1, '=PIVOT(%s,30,TRUE,FALSE)' % assets)
    dashboard.col_sizes.update({0: 330, 1: 170, 2: 170, 3: 170})
    return workbook


DASHBOARDS = {
    'assets_dashboard.json': build_assets,
}


def main():
    os.makedirs(FILES, exist_ok=True)
    for file_name, build in DASHBOARDS.items():
        build().dump(os.path.join(FILES, file_name))
        print('written', file_name)


if __name__ == '__main__':
    main()
