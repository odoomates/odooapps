{
    'name': 'Odoo 20 Budget Management - Purchase',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Budget control of purchase orders and committed amounts',
    'description': 'Warn or block purchase orders going over budget and show the amounts committed by confirmed '
                   'purchase orders on the budget lines.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'depends': ['om_account_budget', 'purchase'],
    'data': [
        'views/account_budget_views.xml',
        'views/purchase_order_views.xml',
    ],
    'auto_install': True,
    'images': ['static/description/banner.gif'],
    'installable': True,
}
