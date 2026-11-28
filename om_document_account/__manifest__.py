{
    'name': 'Documents - Accounting',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'Vendor bills, customer invoices and credit notes from documents, and the files of the '
               'invoices in an Accounting folder',
    'description': 'Create a vendor bill, a customer invoice or a credit note from a document, its file as the '
                   'main attachment, and keep the files of the invoices and bills in an Accounting folder.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_document', 'account'],
    'data': [
        'data/om_documents_account_data.xml',
        'views/om_documents_document_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': ['demo/om_documents_account_demo.xml'],
    'installable': True,
    'auto_install': True,
}
