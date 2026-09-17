#!/usr/bin/env python3
""" Write the Budgets dashboard of om_spreadsheet_account_budget into data/files.

    python3 om_spreadsheet_account_budget/tools/build_dashboards.py

It reads the budget lines of om_account_budget, whose actual and theoretical amounts are summed by the
budget module itself.
The builder is the one of om_spreadsheet_account.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'om_spreadsheet_account', 'tools'))

from spreadsheet_builder import (  # noqa: E402
    GREEN, HEADER, INTEGER_FORMAT, PERCENT_FORMAT, RED, TEAL, TEXT, Workbook, dashboard_sheet, label, stable_id,
)

FILES = os.path.join(os.path.dirname(HERE), 'data', 'files')

GAP = 10


def build_budgets():
    workbook = Workbook('budgets')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    period = workbook.date_filter('period', 'Period', 'this_year')
    budget = workbook.relation_filter('budget', 'Budget', 'account.budget')
    matching = {period: ('date_from', 'date'), budget: ('budget_id', 'many2one')}
    live = [['budget_state', 'in', ['confirm', 'validate', 'done']]]
    measures = ['planned_amount', ('theoretical_amount', 'sum'), ('practical_amount', 'sum')]
    totals = workbook.pivot('Budgets by Type', 'account.budget.line', live, measures, columns=['budget_type'],
                            field_matching=matching)
    positions = workbook.pivot('Budgets by Position', 'account.budget.line', live, measures,
                               rows=['budget_type', 'position_id'], field_matching=matching)

    lines = [
        ('expense_planned', 'Planned expenses', 'planned_amount', 'expense'),
        ('expense_theoretical', 'Expenses expected to date', 'theoretical_amount:sum', 'expense'),
        ('expense_actual', 'Actual expenses', 'practical_amount:sum', 'expense'),
        ('revenue_planned', 'Planned revenues', 'planned_amount', 'revenue'),
        ('revenue_theoretical', 'Revenues expected to date', 'theoretical_amount:sum', 'revenue'),
        ('revenue_actual', 'Actual revenues', 'practical_amount:sum', 'revenue'),
    ]
    refs = {}
    for row, (key, text, measure, budget_type) in enumerate(lines):
        data.set(0, row, label(text), TEXT)
        refs[key] = data.set(1, row, '=PIVOT.VALUE(%s,"%s","budget_type","%s")' % (totals, measure, budget_type))
    data.set(0, 6, label('Expenses spent of the plan'), TEXT)
    refs['expense_rate'] = data.set(1, 6, '=IFERROR(B3/B1,0)', fmt=PERCENT_FORMAT)
    data.set(0, 7, label('Revenues earned of the plan'), TEXT)
    refs['revenue_rate'] = data.set(1, 7, '=IFERROR(B6/B4,0)', fmt=PERCENT_FORMAT)
    data.set(0, 8, label('Expenses spent of the plan (%)'), TEXT)
    refs['expense_gauge'] = data.set(1, 8, '=ROUND(B7*100)', fmt=INTEGER_FORMAT)
    data.set(0, 9, label('Revenues earned of the plan (%)'), TEXT)
    refs['revenue_gauge'] = data.set(1, 9, '=ROUND(B8*100)', fmt=INTEGER_FORMAT)
    data.col_sizes.update({0: 260})

    width = 235
    items = [
        # the actual amounts compared with what was expected at this date
        ('expense_actual', 'Actual Expenses', refs['expense_actual'], refs['expense_theoretical'], None, RED, GREEN),
        ('expense_planned', 'Planned Expenses', refs['expense_planned'], None, None, GREEN, RED),
        ('revenue_actual', 'Actual Revenues', refs['revenue_actual'], refs['revenue_theoretical'], None, GREEN, RED),
        ('revenue_planned', 'Planned Revenues', refs['revenue_planned'], None, None, GREEN, RED),
    ]
    figures = {}
    for index, (key, title, value, baseline, _text, up, down) in enumerate(items):
        figures[key] = dashboard.scorecard(key, title, value, index * (width + GAP), 0, width, 110,
                                           baseline=baseline, baseline_text='vs expected to date' if baseline else None)
        dashboard.figures[-1]['data'].update(baselineColorUp=up, baselineColorDown=down)
    for figure in figures.values():
        workbook.link_menu(figure, 'om_account_budget.menu_account_budget')
    for index, (key, title, lower, upper, colors) in enumerate((
            ('expense_gauge', 'Expenses Spent (%)', 80, 100, ('#6aa84f', '#f1c232', '#cc0000')),
            ('revenue_gauge', 'Revenues Earned (%)', 50, 90, ('#cc0000', '#f1c232', '#6aa84f')))):
        figure_id = stable_id(workbook.key, 'figure', key)
        dashboard.add_figure('chart', {
            'type': 'gauge',
            'title': {'text': title, 'bold': True, 'color': TEAL, 'fontSize': 14},
            'background': '',
            'dataRange': refs[key],
            'sectionRule': {
                'colors': {'lowerColor': colors[0], 'middleColor': colors[1], 'upperColor': colors[2]},
                'rangeMin': '0', 'rangeMax': '120',
                'lowerInflectionPoint': {'type': 'number', 'value': str(lower), 'operator': '<='},
                'upperInflectionPoint': {'type': 'number', 'value': str(upper), 'operator': '<='},
            },
            'humanize': True,
            'chartId': figure_id,
        }, index * (width * 2 + 2 * GAP), 120, width * 2 + GAP, 230, figure_id)
    top = 16
    dashboard.set(0, top, label('Budget by Position'), HEADER)
    for col in (1, 2, 3):
        dashboard.set(col, top, None, HEADER)
    dashboard.set(0, top + 1, '=PIVOT(%s,50,TRUE,TRUE)' % positions)
    dashboard.col_sizes.update({0: 330, 1: 170, 2: 170, 3: 170})
    return workbook


DASHBOARDS = {
    'budgets_dashboard.json': build_budgets,
}


def main():
    os.makedirs(FILES, exist_ok=True)
    for file_name, build in DASHBOARDS.items():
        build().dump(os.path.join(FILES, file_name))
        print('written', file_name)


if __name__ == '__main__':
    main()
