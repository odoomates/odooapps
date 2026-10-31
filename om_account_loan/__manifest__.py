{
    'name': 'Loans',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Bank loans: amortization schedule, drawdowns in tranches, instalments, early repayment, '
               'floating rates, current and non-current reclassification, loan report',
    'description': 'Loans received from banks and other lenders, with their amortization schedule and entries.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/account_loan_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/account_loan_drawdown_views.xml',
        'wizard/account_loan_pay_views.xml',
        'wizard/account_loan_repay_views.xml',
        'wizard/account_loan_reclassify_views.xml',
        'report/account_loan_report_views.xml',
        'report/report_loan_templates.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/account_loan_demo.xml'],
    'assets': {
        'web.assets_tests': [
            'om_account_loan/static/tests/tours/**/*',
        ],
    },
    'application': False,
}
