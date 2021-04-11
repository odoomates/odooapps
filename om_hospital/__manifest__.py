# -*- coding: utf-8 -*-
{
    'name': 'Odoo 14 Development Tutorials',
    'version': '14.0.1.0.0',
    'summary': 'Odoo 14 Development Tutorials',
    'sequence': -100,
    'description': """Odoo 14 Development Tutorials""",
    'category': 'Productivity',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'website': 'https://www.odoomates.tech',
    'live_test_url': 'https://www.youtube.com/watch?v=I8FNdellz3Y&list=PLqRRLx0cl0homY1elJbSoWfeQbRKJ-oPO&index=2',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'website_slides',
        'hr'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/slide_data_v12.xml',
        'data/slide_data_v12_2.xml',
        'data/slide_data_v13.xml',
        'data/slide_data_v14.xml',
        'views/patient.xml',
        'views/sale.xml'
    ],
    'demo': [],
    'qweb': [],
    'images': ['static/description/banner.gif'],
    'installable': True,
    'application': True,
    'auto_install': False,
}