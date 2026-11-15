{
    'name': 'Inventory Reports - Expiry',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Lot and serial number expiry report on screen: expired stock, expiring soon, best before, '
               'removal dates, export to PDF and Excel',
    'description': 'Adds a Lot Expiry report to the Inventory Reports, for products with expiration dates.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_inventory_reports', 'product_expiry'],
    'data': [
        'views/menu.xml',
    ],
    'auto_install': True,
    'installable': True,
    'application': False,
}
