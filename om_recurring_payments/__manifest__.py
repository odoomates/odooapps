{
    'name': 'Odoo 20 Recurring Payment',
    'author': 'Odoo Mates',
    'category': 'Accounting',
    'version': '1.0.1',
    'description': """Odoo 20 Recurring Payment, Recurring Payment In Odoo, Odoo 20 Accounting""",
    'summary': 'Use recurring payments to handle periodically repeated payments',
    'sequence': 11,
    'depends': ['account'],
    'license': 'LGPL-3',
    'data': [
        'data/sequence.xml',
        'data/recurring_cron.xml',
        'security/ir.access.csv',
        'views/recurring_template_view.xml',
        'views/recurring_payment_view.xml'
    ],
    'images': ['static/description/banner.png'],
}
