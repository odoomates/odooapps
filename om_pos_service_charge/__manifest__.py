# -*- coding: utf-8 -*-

{
    'name': 'Pos Service Charge',
    'version': '12.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Service Charges In POS',
    'description': """Service charges in pos""",
    'depends': ['point_of_sale'],
    'author': 'Odoo Mates',
    'company': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'website': 'http://odoomates.tech',
    'support': 'odoomates@gmail.com',
    'data': [
        'views/pos.xml',
        'views/pos_templates.xml'
    ],
    'qweb': [
        'static/src/xml/*.xml',
    ],
    'images': ['static/description/banner.png'],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
