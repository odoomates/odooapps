{
    'name': 'Quick Add Products - Purchase',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Paste lines, scan barcodes, re-order what the vendor supplied before and copy lines on purchase orders',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_quick_add', 'purchase'],
    'data': [
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
