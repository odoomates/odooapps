{
    'name': 'Shiprocket Shipping Connector',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Shiprocket, Shiprocket Connector, Shiprocket Integration, India shipping, courier aggregator, '
               'shipping rates, AWB, shipping labels, manifest, pickup, tracking, cash on delivery',
    'description': 'Ship with many Indian couriers through your own Shiprocket account: live rates on quotations '
                   'and at checkout, courier choice, AWB, pickup, label and manifest on validation, tracking and '
                   'cancellation.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['stock_delivery'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
}
