{
    'name': 'Sign: Print Templates',
    'version': '1.0.0',
    'category': 'Productivity',
    'summary': 'Send the issued prints for signature: the signers of each print template, signatures at their '
               'placeholders in the text',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_sign', 'om_print_template'],
    'data': [
        'security/ir.access.csv',
        'report/sign_reports.xml',
        'views/print_views.xml',
        'views/sign_request_views.xml',
        'views/sign_templates.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/om_sign_print_template_demo.xml'],
    'images': ['static/description/banner.gif'],
    'auto_install': True,
}
