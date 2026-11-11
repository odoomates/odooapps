{
    'name': 'Batch Payments Reconciliation',
    'version': '0.1.0',
    'category': 'Accounting',
    'summary': 'Reconcile one Bank Transaction with all the Payments of a Batch',
    'description': 'Adds a Batches tab to the reconciliation screen of Odoo 20 Reconciliation: one transaction of '
                   'the bank reconciled with all the payments of a batch, suggested and reconciled automatically '
                   'when its reference and amount match.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['om_account_batch_payment', 'om_account_reconcile'],
    'data': [
        'views/account_batch_payment_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_account_batch_payment_reconcile/static/src/bank_reconciliation/*',
        ],
        'web.assets_tests': [
            'om_account_batch_payment_reconcile/static/tests/tours/**/*',
        ],
    },
    'auto_install': True,
    'images': ['static/description/banner.png'],
    'installable': True,
}
