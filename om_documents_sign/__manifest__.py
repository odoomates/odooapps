{
    'name': 'Documents - Sign',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Request a signature on a PDF document, the signed PDF saved back as a new version',
    'description': 'Send a PDF of Documents for electronic signature: once everyone signed, the signed PDF becomes '
                   'the new version of the document.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_documents', 'om_sign'],
    'data': [
        'data/om_documents_sign_data.xml',
        'views/om_documents_document_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
