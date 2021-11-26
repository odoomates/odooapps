# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo 15 Accounting',
    'version': '2.1.0',
    'category': 'Accounting',
    'summary': 'Accounting Reports, Asset Management and Account Budget, Recurring Payments, '
               'Lock Dates, Fiscal Year For Odoo15 Community Edition',
    'description': 'Odoo 15 Financial Reports, Asset Management and '
                   'Account Budget For Odoo15 Community Edition',
    'live_test_url': 'https://www.youtube.com/watch?v=Kj4hR7_uNs4',
    'sequence': '1',
    'website': 'https://www.odoomates.tech',
    'author': 'Odoo Mates, Odoo SA',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': [
        'accounting_pdf_reports',
        'om_account_asset',
        'om_account_budget',
        'om_fiscal_year',
        'om_recurring_payments',
        'om_account_bank_statement_import'
    ],
    'demo': [],
    'data': [
        'views/settings.xml',
        'views/account_type.xml',
        'views/account_group.xml',
        'views/account_tag.xml',
        'views/res_partner.xml',
        'views/account_bank_statement.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.gif'],
}

