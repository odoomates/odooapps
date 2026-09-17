#!/usr/bin/env python3
""" Write the Follow-ups and Cash Forecast dashboard of om_spreadsheet_account_followup into data/files.

    python3 om_spreadsheet_account_followup/tools/build_dashboards.py

It reads the follow-up analysis of om_account_followup, the cash forecast items of om_account_cash_forecast
and the aged balance of om_spreadsheet_account.
The builder is the one of om_spreadsheet_account.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'om_spreadsheet_account', 'tools'))

from spreadsheet_builder import (  # noqa: E402
    GREEN, HEADER, HEADER_RIGHT, RED, TEXT, Workbook, cards, dashboard_sheet, label,
)

FILES = os.path.join(os.path.dirname(HERE), 'data', 'files')

DATE_FORMAT = 'mm/dd/yyyy'
MONTH_FORMAT = 'mmm yyyy'


AGED_MODEL = 'om.spreadsheet.aged.balance'


def build_followups_forecast():
    workbook = Workbook('followups_forecast')
    dashboard = dashboard_sheet(workbook)
    data = workbook.sheet('Data')
    partner = workbook.relation_filter('partner', 'Partner', 'res.partner')
    matching = {partner: ('partner_id', 'many2one')}
    levels = workbook.pivot('Balance by Follow-up Level', 'followup.stat', [['balance', '!=', 0]], ['balance'],
                            rows=['followup_id'], field_matching=matching)
    receipts = workbook.pivot(
        'Expected Receipts', AGED_MODEL, [['partner_type', '=', 'customer'], ['bucket', '=', 'not_due']],
        ['amount_residual'], rows=[('date_maturity', 'month')], field_matching=matching)
    payments = workbook.pivot(
        'Expected Payments', AGED_MODEL, [['partner_type', '=', 'vendor'], ['bucket', '=', 'not_due']],
        ['amount_residual'], rows=[('date_maturity', 'month')], field_matching=matching)
    overdue = workbook.pivot(
        'Overdue', AGED_MODEL, [['bucket', '!=', 'not_due']], ['amount_residual'], columns=['partner_type'],
        field_matching=matching)
    items = workbook.odoo_list(
        'Cash Forecast Items', 'account.cash.forecast.item', [],
        [('date', 'Expected On'), ('name', 'Description'), ('direction', 'Type'), ('amount', 'Amount'),
         ('recurrence', 'Recurrence'), ('date_end', 'Until'), ('partner_id', 'Partner')],
        order_by=[('date', True)], field_matching=matching)

    data.set(0, 0, label('Overdue receivables'), TEXT)
    overdue_receivable = data.set(1, 0, '=PIVOT.VALUE(%s,"amount_residual","partner_type","customer")' % overdue)
    data.set(0, 1, label('Overdue payables'), TEXT)
    overdue_payable = data.set(1, 1, '=PIVOT.VALUE(%s,"amount_residual","partner_type","vendor")' % overdue)
    data.set(0, 2, label('Receipts expected in 6 months'), TEXT)
    expected_receipts = data.set(1, 2, '=SUM(E2:E7)')
    data.set(0, 3, label('Payments expected in 6 months'), TEXT)
    expected_payments = data.set(1, 3, '=SUM(F2:F7)')
    data.set(0, 4, label('First month'), TEXT)
    data.set(1, 4, '=DATE(YEAR(TODAY()),MONTH(TODAY()),1)', fmt=DATE_FORMAT)
    data.set(3, 0, label('Due Month'), HEADER)
    data.set(4, 0, label('Receipts'), HEADER_RIGHT)
    data.set(5, 0, label('Payments'), HEADER_RIGHT)
    for index in range(6):
        row = 1 + index
        data.set(3, row, '=EDATE($B$5,%s)' % index, fmt=MONTH_FORMAT)
        month = 'TEXT(D%s,"mm/yyyy")' % (row + 1)
        data.set(4, row, '=PIVOT.VALUE(%s,"amount_residual","date_maturity:month",%s)' % (receipts, month))
        data.set(5, row, '=PIVOT.VALUE(%s,"amount_residual","date_maturity:month",%s)' % (payments, month))
    data.col_sizes.update({0: 260, 3: 110})

    items_cards = [
        ('overdue_receivable', 'Overdue Receivables', overdue_receivable, None, None, RED, GREEN),
        ('overdue_payable', 'Overdue Payables', overdue_payable, None, None, RED, GREEN),
        ('expected_receipts', 'Receipts Due in 6 Months', expected_receipts, None, None, GREEN, RED),
        ('expected_payments', 'Payments Due in 6 Months', expected_payments, None, None, RED, GREEN),
    ]
    figures = cards(dashboard, items_cards, 240)
    workbook.link_menu(figures['overdue_receivable'], 'om_account_followup.om_account_followup_s')
    dashboard.chart(
        'due', 'bar', 'Receipts and Payments by Due Month', data.range(3, 1, 3, 6),
        [(data.range(4, 1, 4, 6), 'Receipts', None), (data.range(5, 1, 5, 6), 'Payments', None)],
        0, 120, 590, 320)
    dashboard.odoo_chart(
        'levels', 'pie', 'By Follow-up Level', 'followup.stat', 'balance', ['followup_id'],
        [['balance', '!=', 0]], 600, 120, 360, 320, field_matching=matching,
        action_xmlid='om_account_followup.action_followup_stat')
    top = 20
    dashboard.set(0, top, label('Cash Forecast Items'), HEADER)
    for col in range(1, 7):
        dashboard.set(col, top, None, HEADER)
    dashboard.set(0, top + 1, '=ODOO.LIST(%s,15)' % items)
    dashboard.set(0, top + 18, label('Balance by Follow-up Level'), HEADER)
    dashboard.set(1, top + 18, None, HEADER)
    dashboard.set(0, top + 19, '=PIVOT(%s,20,TRUE,FALSE)' % levels)
    dashboard.col_sizes.update({0: 150, 1: 260, 2: 110, 3: 130, 4: 130, 5: 110, 6: 200})
    return workbook


DASHBOARDS = {
    'followups_forecast_dashboard.json': build_followups_forecast,
}


def main():
    os.makedirs(FILES, exist_ok=True)
    for file_name, build in DASHBOARDS.items():
        build().dump(os.path.join(FILES, file_name))
        print('written', file_name)


if __name__ == '__main__':
    main()
