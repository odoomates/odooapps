# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo12 Accounting',
    'version': '12.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Accounting Reports, Asset Management and Account Budget For Odoo12 Community Edition',
    'sequence': '8',
    'author': 'Odoo Mates, Odoo SA',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'website': '',
    'depends': ['accounting_pdf_reports', 'om_account_asset', 'om_account_budget'],
    'demo': [],
    'data': [
        'views/account.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.gif'],
    'qweb': [],
}
