{
    'name': 'Sale,Purchase Mass Confirm and Cancel',
    'version': '1.0.0',
    'category': 'Generic Modules/Others',
    'description': 'Allow To Cancel and Confirm the Sales and Purchase From the Tree View',
    'summary': 'Allow To Cancel and Confirm the Sales and Purchase From the Tree View',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'website': 'http://odoomates.tech',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'purchase'
    ],
    'data': [
        'views/sale_view.xml',
        'views/purchase_view.xml',
    ],
    'images': ['static/description/banner.png'],
    'demo': [],
    'test': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
