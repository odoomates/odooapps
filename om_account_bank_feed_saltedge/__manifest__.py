{
    'name': 'Bank Feeds: Salt Edge',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Salt Edge bank feeds, Salt Edge connector, Salt Edge integration, open banking, PSD2, '
               'automatic bank synchronization, bank transactions in bank journals, European banks',
    'description': 'Connect thousands of banks through your own Salt Edge account (Account Information API): '
                   'the consent is given on the Salt Edge page, the accounts are mapped to the bank journals, '
                   'and the transactions arrive automatically, without duplicates.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_account_bank_feed'],
    'external_dependencies': {'python': ['requests', 'cryptography']},
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
