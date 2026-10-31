{
    'name': 'Document Expiry',
    'version': '1.0.0',
    'category': 'Productivity',
    'summary': 'Expiring documents on any record, e.g. passports, licenses and permits, with reminders and renewals',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/om_document_security.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/om_document_type_views.xml',
        'views/om_document_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_document/static/src/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
    'application': True,
}
