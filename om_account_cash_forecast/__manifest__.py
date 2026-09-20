{
    'name': 'Odoo 20 Cash Forecast',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Forecast the cash balance by week or month from the invoices, bills and expected payments',
    'description': """
Cash forecast: starting from the bank and cash balance of today, the receipts and payments expected by week or
by month from the due dates of the open customer invoices and vendor bills, the payments not yet in the bank,
the recurring payments and the expected items entered by hand (salaries, rent, loans, taxes...).
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'views/cash_forecast_item_views.xml',
        'wizard/cash_forecast_report_views.xml',
        'report/report_cash_forecast.xml',
    ],
    'images': ['static/description/cash_forecast.png'],
}
