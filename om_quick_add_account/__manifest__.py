{
    'name': 'Quick Add Products - Invoicing',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Paste lines, scan barcodes, re-order from the history and copy lines on invoices and bills',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_quick_add', 'account'],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
