{
    'name': 'Print Templates',
    'version': '1.0.0',
    'category': 'Productivity',
    'summary': 'Print certificates, letters and confirmations from any record: numbered, kept as printed, '
               'with a verification QR code',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail', 'web'],
    'data': [
        'security/om_print_template_security.xml',
        'security/ir.access.csv',
        'report/om_print_issue_report.xml',
        'views/om_print_template_views.xml',
        'views/om_print_issue_views.xml',
        'views/om_print_wizard_views.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/om_print_template_demo.xml'],
    'images': ['static/description/banner.gif'],
    'application': True,
}
