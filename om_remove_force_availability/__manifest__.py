# -*- coding: utf-8 -*-
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'Remove Force Availability Button in Picking',
    'version': '10.0.1.0.0',
    'category': 'Warehouse',
    'description': 'Remove Force Availability Button in Stock Picking',
    'summary': 'Remove Force Availability Button in Stock Picking',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'views/stock_picking.xml',
    ],
    'images': ['static/description/banner.jpg'],
    'demo': [],
    'test': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
