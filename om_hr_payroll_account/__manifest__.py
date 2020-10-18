#-*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo 14 HR Payroll Accounting',
    'category': 'Human Resources',
    'author': 'Odoo Mates, Odoo SA',
    'version': '14.0.1.1.0',
    'website': 'https://www.odoomates.tech',
    'description': """
Generic Payroll system Integrated with Accounting.
==================================================

    * Expense Encoding
    * Payment Encoding
    * Company Contribution Management
    """,
    'depends': ['om_hr_payroll', 'account'],
    'data': ['views/hr_payroll_account_views.xml'],
    'demo': [],
    'test': ['../account/test/account_minimal_test.xml'],
    'images': ['static/description/banner.png'],
}
