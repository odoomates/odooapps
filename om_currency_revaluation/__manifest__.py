{
    'name': 'Odoo 20 Currency Revaluation',
    'version': '1.0.1',
    'category': 'Accounting',
    'summary': 'Revalue the open foreign currency balances at the closing rate, with unrealized gains and losses',
    'description': """
Restate what is open in a foreign currency at the rate of a chosen date: the unpaid customer invoices, the unpaid
vendor bills and the balances of the accounts held in a foreign currency, such as the bank accounts.

The difference with the amounts in the books is posted as one adjustment entry, on an unrealized gain account and an
unrealized loss account, and reversed at the start of the next period: nothing is gained or lost until the invoices
are paid. Required by IAS 21 and by most local rules at the closing of a period.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'views/res_config_settings_views.xml',
        'wizard/currency_revaluation_views.xml',
        'views/account_move_views.xml',
    ],
    'images': ['static/description/banner.gif'],
}
