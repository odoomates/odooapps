{
    'name': 'Loans and Leases',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Bank loans and leases: amortization schedule, drawdowns in tranches, instalments, early '
               'repayment, floating rates, lease liability and lessor bills, withholding tax on the interest, '
               'imported schedules, current and non-current reclassification, loan report',
    'description': 'Loans received from banks and other lenders, and leases, with their amortization schedule '
                   'and entries.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/account_loan_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/account_loan_drawdown_views.xml',
        'wizard/account_loan_pay_views.xml',
        'wizard/account_loan_repay_views.xml',
        'wizard/account_loan_reclassify_views.xml',
        'wizard/account_loan_import_views.xml',
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
