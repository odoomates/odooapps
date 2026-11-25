{
    'name': 'Aramex Shipping Connector',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Aramex, Aramex Connector, Aramex Integration, Gulf and Middle East shipping, UAE, Saudi Arabia, '
               'shipping rates, AWB, shipping labels, tracking, cash on delivery, customs value',
    'description': 'Ship with your own Aramex account: live rates on quotations and at checkout, express and '
                   'domestic products, AWB and label on validation, cash on delivery, customs value for '
                   'international shipments and tracking.',
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
