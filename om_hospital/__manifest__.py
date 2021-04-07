# -*- coding: utf-8 -*-
{
    'name': 'Odoo 14 Development Tutorials',
    'version': '1.0',
    'summary': 'Odoo 14 Development Tutorials',
    'sequence': -100,
    'description': """Odoo 14 Development Tutorials""",
    'category': 'Productivity',
    'website': 'https://www.odoomates.tech',
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
