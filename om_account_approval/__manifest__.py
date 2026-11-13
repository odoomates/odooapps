{
    'name': 'Odoo 20 Accounting Approvals',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Vendor bills, credit notes, journal entries and payments posted only once approved',
    'description': 'The approval flows of the Approvals app on the Post button of the journal entries and payments '
                   'hold for every way of posting: the Post action of the lists, the Confirm Entries wizard, the '
                   'auto-post of the scheduled entries and the Register Payment wizard.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account', 'om_approval'],
    'data': [
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
    ],
    'auto_install': True,
    'installable': True,
}
