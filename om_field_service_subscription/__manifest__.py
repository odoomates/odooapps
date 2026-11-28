{
    'name': 'Field Service - Subscriptions',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'summary': 'Maintenance contracts for field service: subscription products that create recurring '
               'maintenance jobs (every N periods, job type with its checklist, preferred technician), jobs '
               'linked to the subscription and covered by the contract instead of billed',
    'description': 'Bridge between Field Service and Subscriptions: a maintenance contract sold as a subscription '
                   'plans its visits by itself, and the work it covers is not invoiced as time and material.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_field_service_sale', 'om_sale_subscription'],
    'data': [
        'data/ir_cron_data.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/project_task_views.xml',
    ],
    'demo': [
        'demo/om_field_service_subscription_demo.xml',
    ],
    'installable': True,
    'auto_install': True,
}
