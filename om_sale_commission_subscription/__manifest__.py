{
    'name': 'Sales Commissions - Subscriptions',
    'version': '20.0.1.0.0',
    'category': 'Sales/Commissions',
    'summary': 'Commissions on subscriptions: monthly recurring revenue (MRR), new MRR, '
               'first period only or every period',
    'description': 'Pay commissions on subscriptions: on the invoiced amount for every period or the first period '
                   'only, on the monthly recurring revenue of the running subscriptions, or on the new and '
                   'expansion MRR of the period.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_sale_commission', 'om_sale_subscription'],
    'data': [
        'views/commission_plan_views.xml',
    ],
    'demo': [
        'demo/commission_demo.xml',
    ],
    'installable': True,
    'auto_install': True,
}
