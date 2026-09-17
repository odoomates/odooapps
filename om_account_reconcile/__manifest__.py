{
    'name': 'Odoo 20 Reconciliation',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Bank Reconciliation, Match Journal Items, Reconciliation Models, Auto Reconciliation',
    'description': 'Reconcile bank and cash transactions with invoices, bills, payments and write-offs, '
                   'and match open journal items, whatever the way the transactions were created.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/account_bank_statement_views.xml',
        'views/bank_reconciliation_views.xml',
        'wizard/reconcile_items_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_account_reconcile/static/src/bank_reconciliation/*',
        ],
        'web.assets_tests': [
            'om_account_reconcile/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
