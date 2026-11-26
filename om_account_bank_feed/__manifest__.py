{
    'name': 'Bank Feeds',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Bank feeds, automatic bank synchronization, bank transactions in bank journals, open banking, '
               'PSD2, bank connection, bank statement sync, scheduled sync, consent renewal',
    'description': 'Fetch the transactions of your bank accounts automatically into the bank journals: connect '
                   'the bank once through a bank feed provider, map its accounts to the journals, and the new '
                   'transactions arrive every few hours, without duplicates, ready to reconcile.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/bank_feed_connection_views.xml',
        'views/bank_feed_log_views.xml',
        'wizard/bank_feed_connect_views.xml',
        'views/account_journal_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
}
