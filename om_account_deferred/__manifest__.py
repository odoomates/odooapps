{
    'name': 'Deferred Revenue and Expense',
    'version': '0.1.1',
    'author': 'Odoo Mates',
    'category': 'Accounting/Accounting',
    'summary': 'Deferred Revenue, Deferred Expense, Prepaid Expenses, Revenue Recognition from the invoice line, '
               'Deferral Entries, Deferred Reports',
    'description': 'Spread revenue and expense over the periods they belong to, from the Start Date and End Date of '
                   'the invoice and bill lines: deferral entries on validation or grouped per period, and the '
                   'Deferred Revenue and Deferred Expense reports.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
        'views/deferred_report_views.xml',
        'report/deferred_report_templates.xml',
    ],
    'images': ['static/description/banner.png'],
}
