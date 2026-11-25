{
    'name': 'Website Subscriptions',
    'version': '20.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Sell subscriptions on your online shop: recurring plans on the product page, recurring '
               'prices in the shop and the cart, saved payment methods at checkout',
    'description': """
Sell the subscription products of the Subscriptions app (om_sale_subscription) on the website shop.
Customers pick a recurring plan on the product page, the cart becomes a subscription, the payment method
is saved at checkout to pay the next invoices, and the subscription starts when the order is paid.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'om_sale_subscription'],
    'data': [
        'views/subscription_plan_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/website_sale_templates.xml',
    ],
    'demo': ['data/website_subscription_demo.xml'],
    'assets': {
        'web.assets_frontend': [
            'om_website_sale_subscription/static/src/interactions/*.js',
            'om_website_sale_subscription/static/src/scss/*.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}
