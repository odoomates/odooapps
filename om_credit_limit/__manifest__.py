# -*- coding: utf-8 -*-

{
    'name': 'Odoo 13 Credit Limit',
    'author': 'Odoo Mates',
    'category': 'Accounting',
    'version': '13.0.3.0.0',
    'description': """Customer Credit Limit""",
    'summary': """Customer Credit Limit""",
    'sequence': 11,
    'company': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'website': 'http://odoomates.tech',
    'depends': ['account', 'sale'],
    'license': 'LGPL-3',
    'data': [
        'views/res_partner.xml',
        'views/account_move.xml',
        'views/sale_order.xml',
        'views/res_config_settings.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
