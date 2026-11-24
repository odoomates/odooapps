{
    'name': 'Rental',
    'version': '20.0.1.0.1',
    'category': 'Sales/Sales',
    'summary': 'Rent products: rental orders with pickup and return dates, hourly, daily, weekly and monthly '
               'prices, availability, late fees, damages, rental schedule, rental agreement, reminders',
    'description': 'Rental orders on top of Sales: rental prices per hour, day, week, month or year with the '
                   'best price for the period, pickup and return, late fees, availability checks, schedule, '
                   'analysis, rental agreement, reminders and customer portal.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'sequence': 31,
    'images': ['static/description/banner.png'],
    'depends': ['sale_management'],
    'data': [
        'security/ir.access.csv',
        'data/product_data.xml',
        'report/rental_agreement_report.xml',
        'data/mail_template_data.xml',
        'data/ir_cron_data.xml',
        'wizard/rental_order_wizard_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/portal_templates.xml',
        'report/rental_report_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/rental_demo.xml',
    ],
    'installable': True,
    'application': True,
}
