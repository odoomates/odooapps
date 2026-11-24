{
    'name': 'Subscriptions',
    'version': '20.0.1.0.1',
    'category': 'Sales/Subscriptions',
    'summary': 'Recurring sales orders: subscription plans, recurring invoices, automatic payments, '
               'upsell, renewal, pause and close, customer portal, MRR, ARR, churn and retention reports',
    'description': 'Sell subscriptions from sales orders: recurring plans, prices per plan, automatic invoices '
                   'and payments with saved payment methods, upsell and renewal quotations, pause and close, '
                   'customer portal and MRR reports.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['sale_management'],
    'data': [
        'security/ir.access.csv',
        'data/subscription_data.xml',
        'data/mail_template_data.xml',
        'data/ir_cron_data.xml',
        'data/portal_entry_data.xml',
        'wizard/subscription_close_wizard_views.xml',
        'views/subscription_plan_views.xml',
        'views/subscription_close_reason_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/sale_order_template_views.xml',
        'views/account_move_views.xml',
        'report/subscription_log_views.xml',
        'report/subscription_report_views.xml',
        'views/subscription_menus.xml',
        'views/portal_templates.xml',
    ],
    'demo': [
        'demo/subscription_demo.xml',
    ],
    'installable': True,
    'application': True,
}
