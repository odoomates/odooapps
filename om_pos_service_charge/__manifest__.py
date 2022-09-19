# -*- coding: utf-8 -*-

{
    'name': 'Pos Service Charge',
    'version': '15.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Service Charges In POS',
    'description': """Service charges in pos""",
    'depends': ['point_of_sale'],
    'author': 'Odoo Mates, Sempai Space',
    'company': 'Odoo Mates, Sempai Space',
    'maintainer': 'Odoo Mates, Sempai Space',
    'website': 'http://odoomates.tech, https://www.sempai.space',
    'support': 'odoomates@gmail.com, sempaispace@gmail.com',
    'data': [
        'views/pos.xml',
    ],
    'assets': {
        'point_of_sale.assets': [
            'om_pos_service_charge/static/src/js/PosServiceChargeButton.js',
        ],
    'web.assets_qweb': [
        'om_pos_service_charge/static/src/xml/PosServiceChargeButton.xml',
     ],
    },
    'images': ['static/description/banner.png'],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
