{
    'name': '3-Way Matching of Vendor Bills',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': '3-way matching of vendor bills with purchase orders and receipts, release to pay, price and '
               'quantity tolerances, bill exceptions, block or warn on payment of bills not released',
    'description': 'Match every vendor bill line with its purchase order line and its receipts: ordered, received '
                   'and billed quantities, PO price against bill price. The bill gets a Release to Pay status '
                   '(Yes, No, Exception) used to block or warn when a payment is registered.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['purchase_stock'],
    'data': [
        'security/ir.access.csv',
        'wizard/om_release_force_wizard_views.xml',
        'views/account_move_views.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/account_payment_register_views.xml',
    ],
    'post_init_hook': '_om_3way_post_init',
    'installable': True,
    'application': False,
}
