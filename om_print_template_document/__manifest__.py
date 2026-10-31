{
    'name': 'Print Templates: Documents',
    'version': '1.0.0',
    'category': 'Productivity',
    'summary': 'File the prints of a template as documents of the record, expiring after a number of days',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_print_template', 'om_document'],
    'data': [
        'views/om_print_template_views.xml',
    ],
    'images': ['static/description/banner.gif'],
    'auto_install': True,
}
