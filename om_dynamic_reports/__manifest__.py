{
    'name': 'Dynamic Accounting Reports',
    'version': '17.0.1.3.1',
    'category': 'Accounting/Accounting',
    'summary': 'Dynamic accounting reports on screen for Odoo 17 Community: Executive Summary, Balance Sheet, Profit and Loss, Cash Flow, '
               'Tax Report, Trial Balance, General Ledger, Day Book, Bank Book, Cash Book, Journals Audit, Partner Ledger, Aged Receivable, Aged Payable, '
               'Analytic Report, Tax Return, EC Sales List, '
               'with comparison, horizontal groups, filters, '
               'drill-down to journal items, saved views and export to PDF and Excel',
    'description': 'Dynamic financial reports: the report on screen with its filters at the top, accounts and '
                   'partners that unfold into their journal items, drill-down, saved views, and export to PDF, '
                   'Excel and CSV as shown.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.gif'],
    'depends': ['om_report_engine', 'accounting_pdf_reports'],
    'data': [
        'security/ir.model.access.csv',
        'views/menu.xml',
        'views/horizontal_group_views.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'om_dynamic_reports/static/tests/tours/*.js',
        ],
    },
    'installable': True,
    'application': False,
}
