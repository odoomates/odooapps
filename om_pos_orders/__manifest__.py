# -*- coding: utf-8 -*-
{
    'name': 'Pos Orders',
    'version': '11.0.1.0.0',
    'summary': """Previous Orders in POS Screen""",
    'description': """Orders in pos screen""",
    'category': 'Point of Sale',
    'live_test_url': 'https://www.youtube.com/watch?v=JUp0BtWuEGg',
    'author': 'Odoo Mates',
    'company': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'website': "",
    'depends': ['point_of_sale', 'pos_longpolling'],
    'data': [
        'views/templates.xml',
    ],
    'images': ['static/description/copy_order_to_cart.gif'],
    'qweb': [
        "static/src/xml/pos_orders.xml",
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
