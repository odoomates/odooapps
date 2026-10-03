{
    'name': 'Odoo 16 Reconciliation',
    'version': '16.0.1.0.0',
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
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/account_bank_statement_views.xml',
        'views/bank_reconciliation_views.xml',
        'wizard/reconcile_items_wizard_views.xml',
        'wizard/bank_reconciliation_report_views.xml',
        'report/report_style.xml',
        'report/report.xml',
        'report/report_bank_reconciliation.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_account_reconcile/static/src/bank_reconciliation/*',
        ],
        'web.assets_tests': [
            'om_account_reconcile/static/tests/tours/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
    'installable': True,
}
