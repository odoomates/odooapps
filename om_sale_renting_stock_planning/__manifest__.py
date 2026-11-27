{
    'name': 'Rental - Stock Planning',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Rent serial numbers as units: each serial number of a rental product is a planning unit, '
               'booked from pickup to return, and the stock moves of the pickup and the return use the '
               'booked serial number',
    'description': 'Links Rental - Planning and Rental - Stock: serial numbers become rental units in the '
                   'planning, so the serial booked on the order is the one that leaves and comes back.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_sale_renting_planning', 'om_sale_renting_stock'],
    'data': [
        'views/product_views.xml',
        'views/stock_lot_views.xml',
        'views/resource_resource_views.xml',
    ],
    'demo': [
        'demo/rental_stock_planning_demo.xml',
    ],
    'installable': True,
    'auto_install': True,
}
