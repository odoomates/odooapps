{
    'name': 'Batch Payments',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Batch Payments, Batch Deposits, Bank Upload Files, one Bank Transaction for many Payments',
    'description': """
Group the payments of a bank journal in a batch: one vendor payment run or one deposit of customer cheques.
Print the payment list or the deposit slip, export the file of the batch for the bulk upload of your bank in a
CSV or Excel layout designed from the settings. With Odoo 18 Reconciliation installed, the bridge Batch Payments
Reconciliation reconciles the single transaction of the bank with all the payments of the batch at once.
    """,
    'sequence': 1,
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_sequence_data.xml',
        'data/batch_layout_data.xml',
        'report/report_batch_payment.xml',
        'views/account_batch_payment_views.xml',
        'views/account_batch_payment_layout_views.xml',
        'views/account_payment_views.xml',
        'views/account_journal_views.xml',
        'wizard/account_payment_register_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
}
