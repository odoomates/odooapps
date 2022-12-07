# -*- coding:utf-8 -*-

{
    'name': 'Odoo 16 HR Payroll Accounting',
    'category': 'Generic Modules/Human Resources',
    'author': 'Odoo Mates, Odoo SA',
    'version': '16.0.1.0.1',
    'sequence': 1,
    'website': 'https://www.odoomates.tech',
    'license': 'LGPL-3',
    'live_test_url': 'https://www.youtube.com/watch?v=0kaHMTtn7oY',
    'summary': 'Generic Payroll system Integrated with Accounting',
    'description': """Generic Payroll system Integrated with Accounting.""",
    'depends': [
        'om_hr_payroll',
        'account'
    ],
    'data': [
        'views/hr_payroll_account_views.xml'
    ],
    'demo': [],
    'test': ['../account/test/account_minimal_test.xml'],
    'images': ['static/description/banner.png'],
    'application': True,
}
