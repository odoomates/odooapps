{
    'name': 'Dynamic Accounting Reports - Currency Revaluation',
    'version': '20.0.1.0.1',
    'category': 'Accounting/Accounting',
    'summary': 'Unrealized currency gains and losses on screen, posted with Currency Revaluation',
    'description': 'Bridge between Dynamic Accounting Reports and Currency Revaluation: what is open in a foreign '
                   'currency at a date, in the books and at the closing rate, with the unrealized gain or loss, '
                   'and the adjustment entry posted from the report.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_dynamic_reports', 'om_currency_revaluation'],
    'data': [
        'views/menu.xml',
    ],
    'images': ['static/description/banner.gif'],
    'installable': True,
    'auto_install': True,
    'application': False,
}
