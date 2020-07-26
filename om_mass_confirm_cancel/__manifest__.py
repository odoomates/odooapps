# -*- coding: utf-8 -*-
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'Sale,Purchase Mass Confirm and Cancel',
    'version': '13.0.1.0.0',
    'category': 'Generic Modules/Others',
    'description': 'Allow To Cancel and Confirm the Sales and Purchase From the Tree View',
    'summary': 'Allow To Cancel and Confirm the Sales and Purchase From the Tree View',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'website': 'http://odoomates.tech',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'sale', 'purchase'
    ],
    'data': [
        'wizards/sale_view.xml',
        'wizards/purchase_view.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [],
    'test': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
