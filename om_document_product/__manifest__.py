{
    'name': 'Documents - Product',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'A folder per product with its sheets, manuals and pictures',
    'description': 'Each product gets its folder in Documents: the files attached to the product, its sheets, '
                   'manuals and certificates, are kept in it.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_document', 'product'],
    'data': [
        'data/om_documents_product_data.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
