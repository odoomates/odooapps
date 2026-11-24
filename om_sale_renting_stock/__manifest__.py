{
    'name': 'Rental - Stock',
    'version': '20.0.1.0.1',
    'category': 'Sales/Sales',
    'summary': 'Rental with inventory: rental location per warehouse, stock moves at pickup and return, '
               'serial numbers, availability from the real stock',
    'description': 'Links Rental and Inventory: pickups move the products from the warehouse to its rental '
                   'location and returns move them back, with lots and serial numbers chosen at pickup and '
                   'expected back at return; availability counts the stock of the warehouse.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_sale_renting', 'sale_stock'],
    'data': [
        'views/stock_warehouse_views.xml',
        'views/sale_order_views.xml',
        'views/product_views.xml',
        'wizard/rental_order_wizard_views.xml',
    ],
    'demo': [
        'demo/rental_stock_demo.xml',
    ],
    'images': ['static/description/banner.png'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': True,
}
