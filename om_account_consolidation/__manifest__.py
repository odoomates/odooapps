{
    'name': 'Consolidation',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Consolidate the companies of a group in one database: group chart and account mapping, '
               'currency translation with a translation reserve, inter-company eliminations, consolidation '
               'periods locked once approved, consolidated trial balance, profit and loss and balance sheet',
    'description': 'Group the companies of the database, map their charts of accounts to one group chart, '
                   'translate their balances into the group currency (closing, average and historical rates), '
                   'eliminate inter-company balances, sales and purchases and dividends, add manual adjustments, '
                   'and read the consolidated trial balance, profit and loss and balance sheet with a column per '
                   'company, the eliminations and the group total, down to the journal items.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_account_inter_company'],
    'data': [
        'security/ir.access.csv',
        'views/consolidation_group_views.xml',
        'views/consolidation_period_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
