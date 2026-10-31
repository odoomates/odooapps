{
    'name': 'Leases: Right-of-use Assets',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'The right-of-use asset of a lease, created at the lease liability and depreciated over the '
               'lease term',
    'description': 'Bridge between Loans and Leases and Assets Management: on the recognition of a lease, its '
                   'right-of-use asset is created in the asset category of the lease and depreciated over the '
                   'lease term.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_account_loan', 'om_account_asset'],
    'data': [
        'views/account_loan_views.xml',
    ],
    'auto_install': True,
}
