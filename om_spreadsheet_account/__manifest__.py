{
    'name': 'Odoo 20 Accounting Dashboards',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Accounting dashboards in the Dashboards app of Odoo 20 Community: overview, profit and loss, '
               'balance sheet, receivables and payables, bank and cash',
    'description': """
Spreadsheet dashboards for accounting in the Dashboards app of Odoo 20 Community Edition: the key figures of the
year, the profit and loss by month, the balance sheet with its ratios, the receivables and payables by age and the
bank and cash movements, all computed from the account types so that they work with any chart of accounts.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['spreadsheet_dashboard_account'],
    'data': [
        'security/ir.access.csv',
        'data/dashboards.xml',
    ],
    'assets': {
        'spreadsheet.o_spreadsheet_core': [
            (
                'after',
                'spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js',
                'om_spreadsheet_account/static/src/**/*.js',
            ),
        ],
    },
    'images': ['static/description/dashboard_overview.png'],
}
