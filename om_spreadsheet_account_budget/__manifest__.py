{
    'name': 'Odoo 20 Budgets Dashboard',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Budgets dashboard in the Dashboards app: planned, expected and actual expenses and revenues',
    'description': """
The Budgets dashboard of the Finance section: the planned, expected and actual expenses and revenues
of the confirmed budgets, the share of the plan used, and the budget by budgetary position.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': [
        'om_spreadsheet_account',
        'om_account_budget',
    ],
    'data': [
        'data/dashboards.xml',
    ],
    'auto_install': True,
    'images': ['static/description/budgets_dashboard.png'],
}
