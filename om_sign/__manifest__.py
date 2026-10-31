{
    'name': 'Sign',
    'version': '2.1.0',
    'category': 'Productivity',
    'summary': 'Send PDF files for electronic signature: fields placed on the PDF, signed in order from an '
               'email link, with a signature certificate',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail', 'portal'],
    'excludes': ['sign'],
    'data': [
        'security/sign_security.xml',
        'security/ir.access.csv',
        'data/sign_data.xml',
        'report/sign_reports.xml',
        'views/sign_templates.xml',
        'views/sign_template_views.xml',
        'views/sign_request_views.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/om_sign_demo.xml'],
    'assets': {
        'web.assets_backend': [
            'om_sign/static/src/template_editor/**/*',
            'om_sign/static/src/views/**/*',
        ],
        'web.assets_frontend': [
            'om_sign/static/src/signing/**/*',
        ],
        'web.assets_tests': [
            'om_sign/static/tests/tours/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
    'application': True,
}
