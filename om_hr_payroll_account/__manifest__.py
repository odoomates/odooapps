{
    'name': 'Odoo 20 HR Payroll Accounting',
    'category': 'Generic Modules/Human Resources',
    'author': 'Odoo Mates, Odoo SA',
    'version': '1.2.2',
    'sequence': 1,
    'license': 'LGPL-3',
    'live_test_url': 'https://www.youtube.com/watch?v=0kaHMTtn7oY',
    'summary': 'Generic Payroll system Integrated with Accounting',
    'description': """Generic Payroll system Integrated with Accounting.""",
    'depends': [
        'om_hr_payroll',
        'account'
    ],
    'data': [
        'security/ir.access.csv',
        'views/hr_payroll_account_views.xml',
        'wizard/hr_payslip_payment_register_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'application': True,
}
