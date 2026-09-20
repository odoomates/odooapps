{
    'name': 'Odoo 20 Follow-ups and Cash Forecast Dashboard',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Follow-ups and cash forecast dashboard in the Dashboards app: overdue balances and expected '
               'receipts and payments',
    'description': """
The Follow-ups and Cash Forecast dashboard of the Finance section: the overdue receivables and
payables, the receipts and payments due in the next six months, the overdue balance by follow-up level and
the cash forecast items.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': [
        'om_spreadsheet_account',
        'om_account_followup',
        'om_account_cash_forecast',
    ],
    'data': [
        'data/dashboards.xml',
    ],
    'auto_install': True,
    'images': ['static/description/followup_dashboard.png'],
}
