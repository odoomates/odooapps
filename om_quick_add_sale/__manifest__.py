{
    'name': 'Quick Add Products - Sales',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Paste lines, scan barcodes, re-order what the customer bought before and copy lines on sales orders',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_quick_add', 'sale'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
