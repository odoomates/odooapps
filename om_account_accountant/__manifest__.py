# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo 14 Accounting',
    'version': '14.0.3.8.0',
    'category': 'Accounting',
    'summary': 'Accounting Reports, Asset Management and Account Budget For Odoo14 Community Edition',
    'live_test_url': 'https://www.youtube.com/watch?v=Kj4hR7_uNs4',
    'sequence': '1',
    'website': 'https://www.odoomates.tech',
    'author': 'Odoo Mates, Odoo SA',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['accounting_pdf_reports', 'om_account_asset',
                'om_account_budget', 'om_account_bank_statement_import'],
    'demo': [],
    'data': [
        'security/ir.model.access.csv',
        'security/account_security.xml',
        'wizard/change_lock_date.xml',
        'views/account.xml',
        'views/account_type.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
    'qweb': [],
}
