#!/usr/bin/env python3
""" Write the dashboards of om_spreadsheet_account into data/files.

    python3 om_spreadsheet_account/tools/build_dashboards.py

The statements (overview, profit and loss, balance sheet) are computed with the OM.ACCOUNT.BALANCE formula of
this module, from the account types: they work with any chart of accounts, add up the companies selected in the
company switcher, and cover the dates of the Period filter, compared with the same period last year or with the
previous period. The other dashboards read pivots, which follow the selected companies as well.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spreadsheet_builder import (  # noqa: E402
    HEADER, HEADER_RIGHT, INTEGER_FORMAT, LINE_BOTTOM, LINE_TOP, NOTE, PERCENT_FORMAT, RATIO_FORMAT, RED, GREEN,
    TEXT, TOTAL, TOTAL_FILL, Workbook, dashboard_sheet, label, quote,
)

FILES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'files')

DATE_FORMAT = 'mm/dd/yyyy'
MONTH_FORMAT = 'mmm yyyy'
CARD_WIDTH = 240
CARD_HEIGHT = 110
GAP = 10
ROW_HEIGHT = 23

INCOME = ('income',)
OTHER_INCOME = ('income_other',)
COST_OF_REVENUE = ('expense_direct_cost',)
EXPENSES = ('expense',)
DEPRECIATION = ('expense_depreciation',)
OTHER_EXPENSES = ('expense_other',)
ALL_EXPENSES = COST_OF_REVENUE + EXPENSES + DEPRECIATION + OTHER_EXPENSES
PROFIT_AND_LOSS = INCOME + OTHER_INCOME + ALL_EXPENSES

# the cells of the Data sheet holding the dates, see period_cells
END = 'Data!$B$2'
START = 'Data!$B$3'
COMPARE_END = 'Data!$B$7'
COMPARE_START = 'Data!$B$8'
FISCAL_START = 'Data!$B$9'
COMPARE_FISCAL_START = 'Data!$B$10'
COMPARE_LABEL = 'Data!$B$12'


def balance(account_types, date_from, date_to, sign=1):
    """ The balance of the accounts of the given types between two dates; an empty start is the beginning """
    formula = 'OM.ACCOUNT.BALANCE(%s,%s,%s)' % (quote(','.join(account_types)), date_from or '""', date_to)
    return '-' + formula if sign < 0 else formula


def card_x(index):
    return index * (CARD_WIDTH + GAP)


def period_cells(workbook, data):
    """ The Period and Compare With filters, and the dates the statements are computed at (rows 1 to 12 of the
    Data sheet). Without a period, the fiscal year to date. """
    workbook.date_filter('period', 'Period', 'year_to_date')
    # the options of the comparison; the default is compared with the first one, whatever the language
    data.set(6, 0, label('Same Period Last Year'), TEXT)
    data.set(6, 1, label('Previous Period'), TEXT)
    workbook.text_filter('compare', 'Compare With', ['Data!G1:G2'], 'Same Period Last Year')

    rows = [
        ('Period', '=ODOO.FILTER.VALUE("Period")', DATE_FORMAT),
        ('End', '=IF(ISNUMBER(C1),C1,TODAY())', DATE_FORMAT),
        ('Start', '=IF(ISNUMBER(B1),B1,ODOO.FISCALYEAR.START(B2))', DATE_FORMAT),
        ('Compare with', '=ODOO.FILTER.VALUE("Compare With")', None),
        ('Previous period', '=B4=G2', None),
        # a period of whole months is compared with as many months before it
        ('Months in the period', '=IF(AND(DAY(B3)=1,B2=EOMONTH(B2,0)),(YEAR(B2)-YEAR(B3))*12+MONTH(B2)-MONTH(B3)+1,0)',
         None),
        ('Comparison end', '=IF(B5,B3-1,EDATE(B2,-12))', DATE_FORMAT),
        ('Comparison start', '=IF(B5,IF(B6,EDATE(B3,-B6),B3-(B2-B3)-1),EDATE(B3,-12))', DATE_FORMAT),
        ('Fiscal year start', '=ODOO.FISCALYEAR.START(B2)', DATE_FORMAT),
        ('Comparison fiscal year start', '=ODOO.FISCALYEAR.START(B7)', DATE_FORMAT),
        ('Description', '=CONCATENATE(TEXT(B3,"mm/dd/yyyy"),_t(" to "),TEXT(B2,"mm/dd/yyyy"),'
                        '_t(", compared with "),TEXT(B8,"mm/dd/yyyy"),_t(" to "),TEXT(B7,"mm/dd/yyyy"))', None),
        ('Comparison', '=IF(B5,_t("Previous Period"),_t("Last Year"))', None),
    ]
    for row, (text, formula, fmt) in enumerate(rows):
        data.set(0, row, label(text), TEXT)
        data.set(1, row, formula, fmt=fmt)
    data.set(2, 0, None, fmt=DATE_FORMAT)
    data.col_sizes.update({0: 200, 1: 130, 2: 130, 6: 180})


def month_rows(data, first_row, count=12):
    """ The months of the period: A the first day, B and C the part of the month in the period, D whether it is in
    the period. :return: the rows """
    data.set(0, first_row - 1, label('Month'), HEADER)
    data.set(1, first_row - 1, label('From'), HEADER)
    data.set(2, first_row - 1, label('To'), HEADER)
    data.set(3, first_row - 1, label('In the period'), HEADER)
    rows = []
    for index in range(count):
        row = first_row + index
        line = row + 1
        data.set(0, row, '=EDATE(DATE(YEAR(%s),MONTH(%s),1),%s)' % (START, START, index), fmt=MONTH_FORMAT)
        data.set(1, row, '=MAX(A%s,%s)' % (line, START), fmt=DATE_FORMAT)
        data.set(2, row, '=MIN(EOMONTH(A%s,0),%s)' % (line, END), fmt=DATE_FORMAT)
        data.set(3, row, '=A%s<=%s' % (line, END))
        rows.append(row)
    return rows


def month_balance(account_types, row, sign=1):
    """ The balance of a month of the period, blank for the months after the period """
    line = row + 1
    return '=IF(Data!$D$%s,%s,"")' % (line, balance(account_types, 'Data!$B$%s' % line, 'Data!$C$%s' % line, sign))


def blank_baseline(data, col, row, source):
    """ A comparison left blank when there is nothing to compare with, rather than an infinite change """
    return data.set(col, row, '=IF(%s=0,"",%s)' % (source, source))


# ---------------------------------------------------------------------------------------------------------------
# Accounting Overview
# ---------------------------------------------------------------------------------------------------------------

def build_overview():
    workbook = Workbook('overview')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    period_cells(workbook, data)

    # key, label, formula of the period, formula of the comparison
    kpis = [
        ('revenue', 'Revenue', balance(INCOME + OTHER_INCOME, START, END, -1),
         balance(INCOME + OTHER_INCOME, COMPARE_START, COMPARE_END, -1)),
        ('cost', 'Cost of Revenue', balance(COST_OF_REVENUE, START, END),
         balance(COST_OF_REVENUE, COMPARE_START, COMPARE_END)),
        ('gross', 'Gross Profit', 'B16-B17', 'C16-C17'),
        ('gross_margin', 'Gross Margin', 'IFERROR(B18/B16,0)', 'IFERROR(C18/C16,0)'),
        ('expenses', 'Expenses', balance(ALL_EXPENSES, START, END),
         balance(ALL_EXPENSES, COMPARE_START, COMPARE_END)),
        ('net', 'Net Profit', 'B16-B20', 'C16-C20'),
        ('net_margin', 'Net Margin', 'IFERROR(B21/B16,0)', 'IFERROR(C21/C16,0)'),
        ('cash', 'Bank and Cash', balance(('asset_cash',), None, END),
         balance(('asset_cash',), None, COMPARE_END)),
        ('receivable', 'Receivables', balance(('asset_receivable',), None, END),
         balance(('asset_receivable',), None, COMPARE_END)),
        ('payable', 'Payables', balance(('liability_payable',), None, END, -1),
         balance(('liability_payable',), None, COMPARE_END, -1)),
        ('current_assets', 'Current Assets',
         balance(('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments'), None, END),
         balance(('asset_cash', 'asset_receivable', 'asset_current', 'asset_prepayments'), None, COMPARE_END)),
        ('current_liabilities', 'Current Liabilities',
         balance(('liability_payable', 'liability_credit_card', 'liability_current'), None, END, -1),
         balance(('liability_payable', 'liability_credit_card', 'liability_current'), None, COMPARE_END, -1)),
        ('current_ratio', 'Current Ratio', 'IFERROR(B26/B27,0)', 'IFERROR(C26/C27,0)'),
    ]
    first = 15
    data.set(0, first - 1, label('Key figures'), HEADER)
    data.set(1, first - 1, label('Period'), HEADER_RIGHT)
    data.set(2, first - 1, label('Comparison'), HEADER_RIGHT)
    data.set(3, first - 1, label('Compared with'), HEADER_RIGHT)
    refs = {}
    for index, (key, text, current, previous) in enumerate(kpis):
        row = first + index
        fmt = PERCENT_FORMAT if key.endswith('margin') else RATIO_FORMAT if key.endswith('ratio') else None
        data.set(0, row, label(text), TEXT)
        data.set(1, row, '=' + current, fmt=fmt)
        data.set(2, row, '=' + previous, fmt=fmt)
        refs[key] = (data.ref(1, row), blank_baseline(data, 3, row, 'C%s' % (row + 1)))

    months = month_rows(data, 31)
    data.set(4, 30, label('Revenue'), HEADER_RIGHT)
    data.set(5, 30, label('Expenses'), HEADER_RIGHT)
    data.set(6, 30, label('Net Profit'), HEADER_RIGHT)
    for row in months:
        data.set(4, row, month_balance(INCOME + OTHER_INCOME, row, -1))
        data.set(5, row, month_balance(ALL_EXPENSES, row))
        data.set(6, row, '=IF(D%s,E%s-F%s,"")' % ((row + 1,) * 3))

    dashboard.set(0, 0, '=Data!B11', NOTE)
    cards = [
        ('revenue', 'Revenue', GREEN, RED), ('gross', 'Gross Profit', GREEN, RED),
        ('expenses', 'Expenses', RED, GREEN), ('net', 'Net Profit', GREEN, RED),
        ('cash', 'Bank and Cash', GREEN, RED), ('receivable', 'Receivables', RED, GREEN),
        ('payable', 'Payables', RED, GREEN), ('current_ratio', 'Current Ratio', GREEN, RED),
    ]
    for index, (key, title, up, down) in enumerate(cards):
        figure = dashboard.scorecard(
            key, title, refs[key][0], card_x(index % 4), 30 + (index // 4) * (CARD_HEIGHT + GAP),
            CARD_WIDTH, CARD_HEIGHT, baseline=refs[key][1], baseline_text='vs comparison')
        dashboard.figures[-1]['data'].update(baselineColorUp=up, baselineColorDown=down)
        if key == 'receivable':
            workbook.link_menu(figure, 'account.menu_action_move_out_invoice_type')
        elif key == 'payable':
            workbook.link_menu(figure, 'account.menu_action_move_in_invoice_type')
    last = months[-1]
    dashboard.chart(
        'monthly', 'combo', 'Revenue and Expenses by Month', data.range(0, months[0], 0, last),
        [(data.range(4, months[0], 4, last), 'Revenue', {'type': 'bar'}),
         (data.range(5, months[0], 5, last), 'Expenses', {'type': 'bar'}),
         (data.range(6, months[0], 6, last), 'Net Profit', {'type': 'line'})],
        0, 280, 4 * CARD_WIDTH + 3 * GAP, 400)
    dashboard.col_sizes.update({0: 250})
    return workbook


# ---------------------------------------------------------------------------------------------------------------
# Profit and Loss
# ---------------------------------------------------------------------------------------------------------------

PNL_LINES = [
    # key, label, account types, sign, kind
    ('income', 'Revenue', INCOME, -1, 'line'),
    ('other_income', 'Other Income', OTHER_INCOME, -1, 'line'),
    ('total_income', 'Total Income', ('income', 'other_income'), 1, 'sum'),
    ('cost', 'Cost of Revenue', COST_OF_REVENUE, 1, 'line'),
    ('gross', 'Gross Profit', ('total_income', '-cost'), 1, 'sum'),
    ('expenses', 'Operating Expenses', EXPENSES, 1, 'line'),
    ('depreciation', 'Depreciation', DEPRECIATION, 1, 'line'),
    ('other_expenses', 'Other Expenses', OTHER_EXPENSES, 1, 'line'),
    ('total_expenses', 'Total Expenses', ('cost', 'expenses', 'depreciation', 'other_expenses'), 1, 'sum'),
    ('net', 'Net Profit', ('total_income', '-total_expenses'), 1, 'grand'),
    ('gross_margin', 'Gross Margin', ('gross', 'total_income'), 1, 'ratio'),
    ('net_margin', 'Net Margin', ('net', 'total_income'), 1, 'ratio'),
]


def build_profit_and_loss():
    workbook = Workbook('profit_and_loss')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    period_cells(workbook, data)
    months = month_rows(data, 15)

    dashboard.set(0, 0, '=Data!B11', NOTE)
    top = 16  # the table starts under the chart
    header = top
    period_col, compare_col, change_col = 1, 2, 3
    month_cols = list(range(4, 4 + len(months)))
    dashboard.set(0, header, label('Profit and Loss'), HEADER)
    for col, row in zip(month_cols, months):
        dashboard.set(col, header, '=IF(Data!D%s,Data!A%s,"")' % (row + 1, row + 1), HEADER_RIGHT, fmt=MONTH_FORMAT)
    dashboard.set(period_col, header, label('Period'), HEADER_RIGHT)
    dashboard.set(compare_col, header, '=' + COMPARE_LABEL, HEADER_RIGHT)
    dashboard.set(change_col, header, label('Change'), HEADER_RIGHT)

    rows = {}
    for index, (key, text, members, sign, kind) in enumerate(PNL_LINES):
        row = header + 1 + index
        rows[key] = row
        style = {'line': TEXT, 'sum': TOTAL, 'grand': TOTAL_FILL, 'ratio': TEXT}[kind]
        border = LINE_TOP if kind == 'grand' else LINE_BOTTOM
        dashboard.set(0, row, label(text), style, border=border)
        for col in [period_col, compare_col] + month_cols:
            fmt = None
            if kind == 'line':
                if col == period_col:
                    formula = '=' + balance(members, START, END, sign)
                elif col == compare_col:
                    formula = '=' + balance(members, COMPARE_START, COMPARE_END, sign)
                else:
                    formula = month_balance(members, months[col - month_cols[0]], sign)
            elif kind == 'ratio':
                part, whole = members
                part_ref = dashboard.ref(col, rows[part], sheet=False)
                whole_ref = dashboard.ref(col, rows[whole], sheet=False)
                formula = '=IF(%s="","",IFERROR(%s/%s,0))' % (whole_ref, part_ref, whole_ref)
                fmt = PERCENT_FORMAT
            else:
                terms = []
                for member in members:
                    negative = member.startswith('-')
                    terms.append(('-' if negative else '+') + dashboard.ref(col, rows[member.lstrip('-')],
                                                                            sheet=False))
                total = ''.join(terms).lstrip('+')
                first_ref = dashboard.ref(col, rows[members[0].lstrip('-')], sheet=False)
                formula = '=IF(%s="","",%s)' % (first_ref, total)
            dashboard.set(col, row, formula, style, fmt=fmt, border=border)
        if kind != 'ratio':
            current = dashboard.ref(period_col, row, sheet=False)
            previous = dashboard.ref(compare_col, row, sheet=False)
            dashboard.set(change_col, row, '=IFERROR((%s-%s)/ABS(%s),"")' % (current, previous, previous), style,
                          fmt=PERCENT_FORMAT, border=border)
        else:
            dashboard.set(change_col, row, None, style, border=border)
    dashboard.col_sizes.update({0: 190, period_col: 110, compare_col: 120, change_col: 80,
                                **{col: 90 for col in month_cols}})
    dashboard.row_sizes.update({header: 30})

    dashboard.chart(
        'monthly', 'combo', 'Income, Expenses and Net Profit by Month',
        dashboard.range(month_cols[0], header, month_cols[-1], header),
        [(dashboard.range(month_cols[0], rows[key], month_cols[-1], rows[key]), text, {'type': chart_type})
         for key, text, chart_type in (('total_income', 'Total Income', 'bar'),
                                       ('total_expenses', 'Total Expenses', 'bar'), ('net', 'Net Profit', 'line'))],
        0, 30, 1180, top * ROW_HEIGHT - 40)
    return workbook


# ---------------------------------------------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------------------------------------------

BALANCE_LINES = [
    ('assets_title', 'Assets', None, 1, 'title'),
    ('cash', 'Bank and Cash', ('asset_cash',), 1, 'line'),
    ('receivable', 'Receivables', ('asset_receivable',), 1, 'line'),
    ('current', 'Current Assets', ('asset_current',), 1, 'line'),
    ('prepayments', 'Prepayments', ('asset_prepayments',), 1, 'line'),
    ('total_current_assets', 'Total Current Assets', ('cash', 'receivable', 'current', 'prepayments'), 1, 'sum'),
    ('fixed', 'Fixed Assets', ('asset_fixed',), 1, 'line'),
    ('non_current', 'Non-current Assets', ('asset_non_current',), 1, 'line'),
    ('total_assets', 'Total Assets', ('total_current_assets', 'fixed', 'non_current'), 1, 'grand'),
    ('liabilities_title', 'Liabilities', None, 1, 'title'),
    ('payable', 'Payables', ('liability_payable',), -1, 'line'),
    ('credit_card', 'Credit Cards', ('liability_credit_card',), -1, 'line'),
    ('current_liabilities', 'Current Liabilities', ('liability_current',), -1, 'line'),
    ('total_current_liabilities', 'Total Current Liabilities', ('payable', 'credit_card', 'current_liabilities'),
     1, 'sum'),
    ('non_current_liabilities', 'Non-current Liabilities', ('liability_non_current',), -1, 'line'),
    ('total_liabilities', 'Total Liabilities', ('total_current_liabilities', 'non_current_liabilities'), 1, 'grand'),
    ('equity_title', 'Equity', None, 1, 'title'),
    ('capital', 'Capital and Reserves', ('equity', 'equity_unaffected'), -1, 'line'),
    # the profit and loss of the fiscal year, not closed into the equity yet
    ('current_earnings', 'Current Year Earnings', PROFIT_AND_LOSS, -1, 'earnings'),
    # what is left once the rest is counted: the earnings of the years not closed yet into the equity
    ('previous_earnings', 'Previous Years Unallocated Earnings',
     ('total_assets', '-total_liabilities', '-capital', '-current_earnings'), 1, 'sum'),
    ('total_equity', 'Total Equity', ('capital', 'current_earnings', 'previous_earnings'), 1, 'grand'),
    ('total_liabilities_equity', 'Total Liabilities and Equity', ('total_liabilities', 'total_equity'), 1, 'grand'),
]


def build_balance_sheet():
    workbook = Workbook('balance_sheet')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    period_cells(workbook, data)

    dashboard.set(0, 0, '=CONCATENATE(_t("Balance at "),TEXT(Data!B2,"mm/dd/yyyy"),_t(", compared with "),'
                        'TEXT(Data!B7,"mm/dd/yyyy"))', NOTE)
    top = 7
    dashboard.set(0, top, label('Balance Sheet'), HEADER)
    dashboard.set(1, top, '=TEXT(%s,"mm/dd/yyyy")' % END, HEADER_RIGHT)
    dashboard.set(2, top, '=TEXT(%s,"mm/dd/yyyy")' % COMPARE_END, HEADER_RIGHT)
    dashboard.set(3, top, label('Change'), HEADER_RIGHT)
    rows = {}
    dates = {1: (FISCAL_START, END), 2: (COMPARE_FISCAL_START, COMPARE_END)}
    for index, (key, text, members, sign, kind) in enumerate(BALANCE_LINES):
        row = top + 1 + index
        rows[key] = row
        if kind == 'title':
            dashboard.set(0, row, label(text), HEADER)
            for col in (1, 2, 3):
                dashboard.set(col, row, None, HEADER)
            continue
        style = {'line': TEXT, 'earnings': TEXT, 'sum': TEXT, 'grand': TOTAL_FILL}[kind]
        border = LINE_TOP if kind == 'grand' else LINE_BOTTOM
        dashboard.set(0, row, label(text), style, border=border)
        for col, (fiscal_start, end) in dates.items():
            if kind == 'line':
                formula = '=' + balance(members, None, end, sign)
            elif kind == 'earnings':
                formula = '=' + balance(members, fiscal_start, end, sign)
            else:
                terms = []
                for member in members:
                    negative = member.startswith('-')
                    terms.append(('-' if negative else '+') + dashboard.ref(col, rows[member.lstrip('-')],
                                                                            sheet=False))
                formula = ''.join(terms).lstrip('+')
                if key == 'previous_earnings':
                    # what is left of the other lines: no rounding noise such as -0.00
                    formula = 'ROUND(%s,6)+0' % formula
                formula = '=' + formula
            dashboard.set(col, row, formula, style, border=border)
        dashboard.set(3, row, '=%s-%s' % (dashboard.ref(1, row, sheet=False), dashboard.ref(2, row, sheet=False)),
                      style, border=border)
    dashboard.col_sizes.update({0: 280, 1: 140, 2: 140, 3: 140})

    ref = lambda key, col=1: dashboard.ref(col, rows[key])  # noqa: E731
    ratios = [
        ('current_ratio', 'Current Ratio', '=IFERROR(%s/%s,0)' % (ref('total_current_assets'),
                                                                   ref('total_current_liabilities'))),
        ('quick_ratio', 'Quick Ratio', '=IFERROR((%s+%s)/%s,0)' % (ref('cash'), ref('receivable'),
                                                                    ref('total_current_liabilities'))),
        ('debt_equity', 'Debt to Equity', '=IFERROR(%s/%s,0)' % (ref('total_liabilities'), ref('total_equity'))),
    ]
    first = 15
    data.set(0, first - 1, label('Ratios'), HEADER)
    ratio_refs = {}
    for index, (key, text, formula) in enumerate(ratios):
        row = first + index
        data.set(0, row, label(text), TEXT)
        ratio_refs[key] = data.set(1, row, formula, fmt=RATIO_FORMAT)

    # a chart reads contiguous ranges: the totals are copied next to each other
    data.set(3, first - 1, label('Structure'), HEADER)
    data.set(4, first - 1, label('Period'), HEADER_RIGHT)
    data.set(5, first - 1, label('Comparison'), HEADER_RIGHT)
    data.set(6, first - 1, label('Compared with'), HEADER_RIGHT)
    baselines = {}
    for index, key in enumerate(('total_assets', 'total_liabilities', 'total_equity')):
        row = first + index
        data.set(3, row, '=' + dashboard.ref(0, rows[key]), TEXT)
        data.set(4, row, '=' + ref(key))
        data.set(5, row, '=' + ref(key, 2))
        baselines[key] = blank_baseline(data, 6, row, 'F%s' % (row + 1))

    cards = [
        ('total_assets', 'Total Assets', ref('total_assets'), baselines['total_assets']),
        ('total_liabilities', 'Total Liabilities', ref('total_liabilities'), baselines['total_liabilities']),
        ('total_equity', 'Total Equity', ref('total_equity'), baselines['total_equity']),
        ('current_ratio', 'Current Ratio', ratio_refs['current_ratio'], None),
        ('quick_ratio', 'Quick Ratio', ratio_refs['quick_ratio'], None),
        ('debt_equity', 'Debt to Equity', ratio_refs['debt_equity'], None),
    ]
    width = 190
    for index, (key, title, value, baseline) in enumerate(cards):
        dashboard.scorecard(key, title, value, index * (width + GAP), 30, width, CARD_HEIGHT, baseline=baseline,
                            baseline_text='vs comparison' if baseline else None)
    dashboard.chart(
        'structure', 'bar', 'Assets, Liabilities and Equity', data.range(3, first, 3, first + 2),
        [(data.range(4, first, 4, first + 2), 'Period', None),
         (data.range(5, first, 5, first + 2), 'Comparison', None)],
        720, (top + 1) * ROW_HEIGHT, 440, 320)
    return workbook


# ---------------------------------------------------------------------------------------------------------------
# Receivables and Payables
# ---------------------------------------------------------------------------------------------------------------

BUCKETS = [
    ('not_due', 'Not Due'),
    ('1_30', '1-30 Days'),
    ('31_60', '31-60 Days'),
    ('61_90', '61-90 Days'),
    ('over_90', 'Over 90 Days'),
]
AGED_MODEL = 'om.spreadsheet.aged.balance'


def build_receivables_payables():
    workbook = Workbook('receivables_payables')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    period = workbook.date_filter('period', 'Period', 'this_year')
    partner = workbook.relation_filter('partner', 'Partner', 'res.partner')

    aged_matching = {partner: ('partner_id', 'many2one')}
    customers = workbook.pivot('Customers by Age', AGED_MODEL, [['partner_type', '=', 'customer']],
                               ['amount_residual'], columns=['bucket'], field_matching=aged_matching)
    vendors = workbook.pivot('Vendors by Age', AGED_MODEL, [['partner_type', '=', 'vendor']],
                             ['amount_residual'], columns=['bucket'], field_matching=aged_matching)
    overdue_customers = workbook.pivot(
        'Overdue Customers', AGED_MODEL, [['partner_type', '=', 'customer'], ['bucket', '!=', 'not_due']],
        ['amount_residual'], rows=['partner_id'], field_matching=aged_matching,
        sorted_column=('amount_residual', 'desc'))
    overdue_vendors = workbook.pivot(
        'Overdue Vendors', AGED_MODEL, [['partner_type', '=', 'vendor'], ['bucket', '!=', 'not_due']],
        ['amount_residual'], rows=['partner_id'], field_matching=aged_matching,
        sorted_column=('amount_residual', 'desc'))
    invoice_matching = {period: ('invoice_date', 'date'), partner: ('commercial_partner_id', 'many2one')}
    invoiced = workbook.pivot(
        'Invoiced', 'account.move',
        [['move_type', 'in', ['out_invoice', 'out_refund']], ['state', '=', 'posted']],
        ['amount_untaxed_signed'], rows=[('invoice_date', 'month')], field_matching=invoice_matching)
    billed = workbook.pivot(
        'Billed', 'account.move',
        [['move_type', 'in', ['in_invoice', 'in_refund']], ['state', '=', 'posted']],
        ['amount_untaxed_signed'], rows=[('invoice_date', 'month')], field_matching=invoice_matching)

    # ageing
    data.set(0, 0, label('Age'), HEADER)
    data.set(1, 0, label('Customers'), HEADER_RIGHT)
    data.set(2, 0, label('Vendors'), HEADER_RIGHT)
    for index, (bucket, text) in enumerate(BUCKETS):
        row = 1 + index
        data.set(0, row, label(text), TEXT)
        data.set(1, row, '=PIVOT.VALUE(%s,"amount_residual","bucket","%s")' % (customers, bucket))
        data.set(2, row, '=PIVOT.VALUE(%s,"amount_residual","bucket","%s")' % (vendors, bucket))
    data.set(0, 6, label('Total'), TOTAL)
    total_receivable = data.set(1, 6, '=PIVOT.VALUE(%s,"amount_residual")' % customers, TOTAL)
    total_payable = data.set(2, 6, '=PIVOT.VALUE(%s,"amount_residual")' % vendors, TOTAL)
    data.set(0, 7, label('Overdue'), TOTAL)
    overdue_receivable = data.set(1, 7, '=B7-B2', TOTAL)
    overdue_payable = data.set(2, 7, '=C7-C2', TOTAL)

    # days sales and payables outstanding, from the fiscal year to date of the current company
    data.set(0, 9, label('Days elapsed in the fiscal year'), TEXT)
    data.set(1, 9, '=TODAY()-ODOO.FISCALYEAR.START(TODAY())+1', fmt=INTEGER_FORMAT)
    data.set(0, 10, label('Revenue of the fiscal year'), TEXT)
    data.set(1, 10, '=' + balance(INCOME, 'ODOO.FISCALYEAR.START(TODAY())', 'TODAY()', -1))
    data.set(0, 11, label('Purchases of the fiscal year'), TEXT)
    data.set(1, 11, '=' + balance(COST_OF_REVENUE + EXPENSES, 'ODOO.FISCALYEAR.START(TODAY())', 'TODAY()'))
    data.set(0, 12, label('Days Sales Outstanding'), TEXT)
    dso = data.set(1, 12, '=ROUND(IFERROR(B7/B11*B10,0))', fmt=INTEGER_FORMAT)
    data.set(0, 13, label('Days Payables Outstanding'), TEXT)
    dpo = data.set(1, 13, '=ROUND(IFERROR(C7/B12*B10,0))', fmt=INTEGER_FORMAT)

    # the months of the period
    data.set(3, 0, label('Month'), HEADER)
    data.set(4, 0, label('Invoiced'), HEADER_RIGHT)
    data.set(5, 0, label('Billed'), HEADER_RIGHT)
    data.set(3, 14, label('Period start'), TEXT)
    data.set(4, 14, '=ODOO.FILTER.VALUE("Period")', fmt=DATE_FORMAT)
    data.set(3, 15, label('First month'), TEXT)
    data.set(4, 15, '=IF(ISNUMBER(E15),DATE(YEAR(E15),MONTH(E15),1),EDATE(DATE(YEAR(TODAY()),MONTH(TODAY()),1),-11))',
             fmt=DATE_FORMAT)
    for index in range(12):
        row = 1 + index
        data.set(3, row, '=EDATE($E$16,%s)' % index, fmt=MONTH_FORMAT)
        month_key = 'TEXT(D%s,"mm/yyyy")' % (row + 1)
        data.set(4, row, '=PIVOT.VALUE(%s,"amount_untaxed_signed","invoice_date:month",%s)' % (invoiced, month_key))
        data.set(5, row, '=-PIVOT.VALUE(%s,"amount_untaxed_signed","invoice_date:month",%s)' % (billed, month_key))
    data.col_sizes.update({0: 200, 3: 110})

    cards = [
        ('receivable', 'Receivables', total_receivable, overdue_receivable, 'overdue', RED, GREEN),
        ('payable', 'Payables', total_payable, overdue_payable, 'overdue', RED, GREEN),
        ('dso', 'Days Sales Outstanding', dso, None, None, RED, GREEN),
        ('dpo', 'Days Payables Outstanding', dpo, None, None, GREEN, RED),
    ]
    for index, (key, title, value, baseline, text, up, down) in enumerate(cards):
        figure = dashboard.scorecard(key, title, value, card_x(index), 0, CARD_WIDTH, CARD_HEIGHT,
                                     baseline=baseline, baseline_text=text,
                                     baseline_mode='text' if baseline else 'percentage')
        dashboard.figures[-1]['data'].update(baselineColorUp=up, baselineColorDown=down)
        if key == 'receivable':
            workbook.link_menu(figure, 'account.menu_action_move_out_invoice_type')
        elif key == 'payable':
            workbook.link_menu(figure, 'account.menu_action_move_in_invoice_type')
    half = 2 * CARD_WIDTH + GAP
    dashboard.chart(
        'ageing', 'bar', 'Open Balances by Age', data.range(0, 1, 0, 5),
        [(data.range(1, 1, 1, 5), 'Customers', None), (data.range(2, 1, 2, 5), 'Vendors', None)],
        0, CARD_HEIGHT + GAP, half, 320)
    dashboard.chart(
        'monthly', 'bar', 'Invoiced and Billed by Month', data.range(3, 1, 3, 12),
        [(data.range(4, 1, 4, 12), 'Invoiced', None), (data.range(5, 1, 5, 12), 'Billed', None)],
        half + GAP, CARD_HEIGHT + GAP, half, 320)

    # the partners owing the most, under the charts
    top = 20
    dashboard.set(0, top, label('Top Overdue Customers'), HEADER)
    dashboard.set(1, top, None, HEADER)
    dashboard.set(3, top, label('Top Overdue Vendors'), HEADER)
    dashboard.set(4, top, None, HEADER)
    dashboard.set(0, top + 1, '=PIVOT(%s,10,FALSE,FALSE)' % overdue_customers)
    dashboard.set(3, top + 1, '=PIVOT(%s,10,FALSE,FALSE)' % overdue_vendors)
    dashboard.col_sizes.update({0: 330, 1: 150, 2: 20, 3: 330, 4: 150})
    return workbook


# ---------------------------------------------------------------------------------------------------------------
# Bank and Cash
# ---------------------------------------------------------------------------------------------------------------

def build_bank_cash():
    workbook = Workbook('bank_cash')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    period = workbook.date_filter('period', 'Period', 'this_year')
    journal = workbook.relation_filter('journal', 'Journal', 'account.journal',
                                       domain=[['type', 'in', ['bank', 'cash', 'credit']]])
    cash_lines = [['parent_state', '=', 'posted'], ['account_id.account_type', '=', 'asset_cash']]
    balances = workbook.pivot('Balance by Account', 'account.move.line', cash_lines, ['balance'],
                              rows=['account_id'], field_matching={journal: ('journal_id', 'many2one')},
                              sorted_column=('balance', 'desc'))
    movements = workbook.pivot('Cash In and Out', 'account.move.line', cash_lines, ['debit', 'credit'],
                               rows=[('date', 'month')],
                               field_matching={period: ('date', 'date'), journal: ('journal_id', 'many2one')})
    to_reconcile = workbook.pivot(
        'Transactions to Reconcile', 'account.bank.statement.line',
        [['is_reconciled', '=', False], ['state', '=', 'posted']], ['__count', 'amount'], rows=['journal_id'],
        field_matching={journal: ('journal_id', 'many2one')})

    data.set(0, 0, label('Bank and cash balance'), TEXT)
    total = data.set(1, 0, '=PIVOT.VALUE(%s,"balance")' % balances)
    data.set(0, 1, label('Cash in'), TEXT)
    cash_in = data.set(1, 1, '=PIVOT.VALUE(%s,"debit")' % movements)
    data.set(0, 2, label('Cash out'), TEXT)
    cash_out = data.set(1, 2, '=PIVOT.VALUE(%s,"credit")' % movements)
    data.set(0, 3, label('Transactions to reconcile'), TEXT)
    count = data.set(1, 3, '=PIVOT.VALUE(%s,"__count")' % to_reconcile, fmt=INTEGER_FORMAT)
    data.set(0, 4, label('Amount to reconcile'), TEXT)
    amount = data.set(1, 4, '=PIVOT.VALUE(%s,"amount")' % to_reconcile)
    data.set(0, 5, label('Period start'), TEXT)
    data.set(1, 5, '=ODOO.FILTER.VALUE("Period")', fmt=DATE_FORMAT)
    data.set(0, 6, label('First month'), TEXT)
    data.set(1, 6, '=IF(ISNUMBER(B6),DATE(YEAR(B6),MONTH(B6),1),EDATE(DATE(YEAR(TODAY()),MONTH(TODAY()),1),-11))',
             fmt=DATE_FORMAT)

    data.set(3, 0, label('Month'), HEADER)
    data.set(4, 0, label('Cash In'), HEADER_RIGHT)
    data.set(5, 0, label('Cash Out'), HEADER_RIGHT)
    data.set(6, 0, label('Net'), HEADER_RIGHT)
    for index in range(12):
        row = 1 + index
        data.set(3, row, '=EDATE($B$7,%s)' % index, fmt=MONTH_FORMAT)
        month_key = 'TEXT(D%s,"mm/yyyy")' % (row + 1)
        data.set(4, row, '=PIVOT.VALUE(%s,"debit","date:month",%s)' % (movements, month_key))
        data.set(5, row, '=PIVOT.VALUE(%s,"credit","date:month",%s)' % (movements, month_key))
        data.set(6, row, '=E%s-F%s' % (row + 1, row + 1))
    data.col_sizes.update({0: 200, 3: 110})

    cards = [
        ('balance', 'Bank and Cash Balance', total, None, None),
        ('cash_in', 'Cash In', cash_in, None, None),
        ('cash_out', 'Cash Out', cash_out, None, None),
        ('to_reconcile', 'Transactions to Reconcile', count, amount, 'amount'),
    ]
    for index, (key, title, value, baseline, text) in enumerate(cards):
        figure = dashboard.scorecard(key, title, value, card_x(index), 0, CARD_WIDTH, CARD_HEIGHT,
                                     baseline=baseline, baseline_text=text,
                                     baseline_mode='text' if baseline else 'percentage')
        if key in ('balance', 'to_reconcile'):
            workbook.link_menu(figure, 'account.menu_board_journal_1')
    dashboard.chart(
        'monthly', 'combo', 'Cash In and Out by Month', data.range(3, 1, 3, 12),
        [(data.range(4, 1, 4, 12), 'Cash In', {'type': 'bar'}),
         (data.range(5, 1, 5, 12), 'Cash Out', {'type': 'bar'}),
         (data.range(6, 1, 6, 12), 'Net', {'type': 'line'})],
        0, CARD_HEIGHT + GAP, 4 * CARD_WIDTH + 3 * GAP, 340)

    top = 21
    dashboard.set(0, top, label('Balance by Account'), HEADER)
    dashboard.set(1, top, None, HEADER)
    dashboard.set(3, top, label('To Reconcile by Journal'), HEADER)
    for col in (4, 5):
        dashboard.set(col, top, None, HEADER)
    dashboard.set(0, top + 1, '=PIVOT(%s,20,TRUE,FALSE)' % balances)
    dashboard.set(3, top + 1, '=PIVOT(%s,20,TRUE,TRUE)' % to_reconcile)
    dashboard.col_sizes.update({0: 330, 1: 150, 2: 20, 3: 260, 4: 130, 5: 130})
    return workbook


DASHBOARDS = {
    'accounting_overview_dashboard.json': build_overview,
    'profit_and_loss_dashboard.json': build_profit_and_loss,
    'balance_sheet_dashboard.json': build_balance_sheet,
    'receivables_payables_dashboard.json': build_receivables_payables,
    'bank_cash_dashboard.json': build_bank_cash,
}


def main():
    os.makedirs(FILES, exist_ok=True)
    for file_name, build in DASHBOARDS.items():
        build().dump(os.path.join(FILES, file_name))
        print('written', file_name)


if __name__ == '__main__':
    main()
