{
    'name': 'Quick Add Products - Inventory',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Paste lines, scan barcodes, the history and copy lines on receipts, deliveries and transfers',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_quick_add', 'stock'],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
