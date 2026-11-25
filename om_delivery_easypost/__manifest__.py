{
    'name': 'EasyPost Shipping Connector',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'EasyPost, EasyPost Connector, EasyPost Integration, USPS, UPS, FedEx, DHL, shipping rates, '
               'shipping labels, PDF and ZPL labels, tracking, customs, insurance, multi-package',
    'description': 'Ship with USPS, UPS, FedEx, DHL and many more carriers through your own EasyPost account: '
                   'live rates on quotations and at checkout, labels in PDF, ZPL or PNG on validation, customs for '
                   'international shipments, insurance, tracking pages and refunds.',
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
