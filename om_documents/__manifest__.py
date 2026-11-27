{
    'name': 'Documents',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Document management: folders with access rights, tags, preview, versions, upload by email, '
               'share links with expiry, upload links, document requests and workflow actions',
    'description': 'Keep the files of the company in folders: drag and drop them, preview them, keep their '
                   'versions, share them with a link, receive them by email and request the missing ones.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['mail', 'portal', 'web'],
    'data': [
        'security/om_documents_security.xml',
        'security/ir.access.csv',
        'data/om_documents_data.xml',
        'views/om_documents_document_views.xml',
        'views/om_documents_folder_views.xml',
        'views/om_documents_tag_views.xml',
        'views/om_documents_share_views.xml',
        'views/om_documents_action_views.xml',
        'views/om_documents_wizard_views.xml',
        'views/om_documents_templates.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/om_documents_demo.xml'],
    'assets': {
        'web.assets_backend': [
            'om_documents/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
