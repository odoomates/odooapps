{
    'name': 'Odoo 14 Credit Limit',
    'author': 'Odoo Mates',
    'category': 'Accounting',
    'version': '1.0.0',
    'description': """Customer Credit Limit""",
    'summary': """Customer Credit Limit""",
    'sequence': 11,
    'website': 'https://www.odoomates.tech',
    'depends': ['account'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'wizard/warning.xml',
        'views/res_partner.xml'
    ],
    'images': ['static/description/banner.png'],

}
