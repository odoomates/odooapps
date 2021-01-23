# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo 13 Accounting',
    'version': '13.0.3.3.0',
    'category': 'Accounting',
    'summary': 'Accounting Reports, Asset Management and Account Budget For Odoo13 Community Edition',
    'live_test_url': 'https://www.youtube.com/watch?v=Kj4hR7_uNs4',
    'sequence': '8',
    'website': 'http://odoomates.tech',
    'author': 'Odoo Mates, Odoo SA',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'website': '',
    'depends': ['accounting_pdf_reports', 'om_account_asset', 'om_account_budget'],
    'demo': [],
    'data': [
        'wizard/change_lock_date.xml',
        'views/account.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
    'qweb': [],
}
