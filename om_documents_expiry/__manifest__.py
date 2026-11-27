{
    'name': 'Documents - Expiry',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Expiring documents with reminders and renewals: passports, licenses, permits, certificates',
    'description': 'Document types with a number, an issue date and an expiry date, reminders before the documents '
                   'expire, renewals, extra files, and a Documents widget on the records keeping them.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_documents'],
    'data': [
        'security/ir.access.csv',
        'data/om_documents_expiry_data.xml',
        'views/om_documents_type_views.xml',
        'views/om_documents_document_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_documents_expiry/static/src/**/*',
        ],
    },
    'installable': True,
}
