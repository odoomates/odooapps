{
    'name': 'Odoo 15 Credit Limit',
    'author': 'Odoo Mates',
    'category': 'Accounting',
    'version': '2.0.0',
    'description': """Customer Credit Limit""",
    'summary': """Customer Credit Limit""",
    'sequence': 11,
    'website': 'https://www.odoomates.tech',
    'depends': ['account', 'sale'],
    'license': 'LGPL-3',
    'data': [
        'views/res_partner.xml',
        'views/account_move.xml',
        'views/sale_order.xml',
        'views/res_config_settings.xml',
    ],
    'images': ['static/description/banner.png'],

}
