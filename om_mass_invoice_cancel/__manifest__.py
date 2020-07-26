# -*- coding: utf-8 -*-
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'Cancel Multiple Invoice',
    'version': '12.0.1.0.0',
    'category': 'Generic Modules/Others',
    'description': 'Allow To Cancel Multiple Invoice From the Tree View',
    'summary': 'Allow To Cancel Multiple Invoice From the Tree View',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
	'website': 'http://odoomates.tech',
    'license': 'LGPL-3',
    'depends': [
        'account', 'account_cancel'
    ],
    'data': [
        'wizards/invoice_view.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [],
    'test': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
