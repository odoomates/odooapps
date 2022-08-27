{
    'name': 'Customer Credit Limit With Warning and Blocking',
    'author': 'Odoo Mates',
    'category': 'Accounting',
    'version': '4.3.0',
    'description': """Customer Credit Limit, Credit Limit With Warning and Blocking, Customer Credit Limit With Warning and Blocking""",
    'summary': """Customer Credit Limit, Credit Limit With Warning and Blocking, Customer Credit Limit With Warning and Blocking""",
    'sequence': 11,
    'website': 'https://www.odoomates.tech',
    'live_test_url': 'https://www.youtube.com/watch?v=wNhWs29T5Zs',
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
