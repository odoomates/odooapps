# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo 14 Accounting',
    'version': '14.0.8.1.0',
    'category': 'Accounting',
    'summary': 'Accounting Reports, Asset Management and Account Budget, Recurring Payments, '
               'Lock Dates, Fiscal Year For Odoo14 Community Edition, Accounting Dashboard, Financial Reports, '
               'Customer Follow up Management, Bank Statement Import, Odoo Budget',
    'description': 'Odoo 14 Financial Reports, Asset Management and '
                   'Account Budget, Financial Reports, Recurring Payments, '
                   'Customer Credit Limit, Bank Statement Import, Customer Follow Up Management,'
                   'Account Lock Date, Accounting Dashboard',
    'live_test_url': 'https://www.youtube.com/watch?v=6gB-05E5kNg',
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
        'om_account_bank_statement_import',
        'om_credit_limit',
        'om_recurring_payments',
        'om_account_followup',
        'om_account_daily_reports',
        ],
    'demo': [],
    'data': [
        'security/ir.model.access.csv',
        'security/account_security.xml',
        'wizard/change_lock_date.xml',
        'views/fiscal_year.xml',
        'views/menu.xml',
        'views/account_settings.xml',
        'views/account_type.xml',
        'views/account_bank_statement.xml',
        'views/account_coa_template.xml',
        'views/account_group.xml',
        'views/account_tag.xml',
        'views/fiscal_position_template.xml',
        'views/res_partner.xml',
        'views/reconciliation.xml',
        'views/payment_method.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.gif'],
    'qweb': [],
}
