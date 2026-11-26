{
    'name': 'Quick Add Products',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Add products to sales orders, purchase orders, invoices, bills and transfers in seconds: '
               'paste a list from Excel or an email, scan barcodes, re-order from the customer or vendor history, '
               'copy lines from another document',
    'description': 'Paste lines: rows of codes, barcodes or names with quantities and prices, from Excel, an email '
                   'or a message, checked before they are added. Scan to add: a scanned product is added to the '
                   'document, or its quantity raised. History: the products the customer bought or the vendor '
                   'supplied, with their last date, quantity and price, added again in one click. Copy lines: the '
                   'lines of any other order, invoice, bill or transfer.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['product', 'barcodes'],
    'data': [
        'security/ir.access.csv',
        'wizard/quick_add_paste_views.xml',
        'wizard/quick_add_history_views.xml',
        'wizard/quick_add_copy_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_quick_add/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
