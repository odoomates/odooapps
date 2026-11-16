{
    'name': 'Dynamic Report Engine',
    'version': '18.0.1.0.1',
    'category': 'Productivity',
    'summary': 'Engine of the Odoo Mates dynamic reports: build on-screen reports with filters, folding, '
               'drill-down, saved views and PDF, Excel and CSV export, in Python only',
    'description': 'The screen, the filters, the table, the saved views and the PDF, Excel and CSV exports of '
                   'the Odoo Mates dynamic reports. A report is a Python model declaring its columns, filters '
                   'and options; no JavaScript to write.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.gif'],
    'depends': ['web'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'report/report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_report_engine/static/src/report/*',
        ],
    },
    'installable': True,
    'application': False,
}
