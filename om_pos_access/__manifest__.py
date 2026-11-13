{
    'name': 'POS Access Control',
    'version': '0.1.1',
    'author': 'Odoo Mates',
    'category': 'Sales/Point of Sale',
    'summary': 'Restrict what each cashier may do in the Point of Sale: refunds, discounts, prices, '
               'cash, closing, customers, payment methods',
    'description': 'Completely free. Set on each user what they may not do in the Point of Sale: refunds, '
                   'discounts and a maximum discount, price changes and a maximum price cut, selling below cost, '
                   'cash in and out, closing the register, creating or editing customers, lowering quantities, '
                   'payment methods. The buttons go from the screen, and the server refuses what is sent anyway.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['point_of_sale'],
    'data': [
        'views/res_users_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'om_pos_access/static/src/**/*',
        ],
    },
}
