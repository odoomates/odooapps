# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Razorpay Payment Acquirer',
    'category': 'Accounting',
    'summary': 'Payment Acquirer: Razorpay Implementation',
    'version': '13.0.1.1.0',
    'author': 'Odoo Mates, Odoo SA',
    'description': """Razorpay Payment Acquirer""",
    'depends': ['payment'],
    'website': 'http://odoomates.tech',
    'live_test_url': 'https://www.youtube.com/watch?v=Zg0EzM-ogQU',
    'application': True,
    'data': [
        'views/payment_views.xml',
        'views/payment_razorpay_templates.xml',
        'data/payment_acquirer_data.xml',
    ],
    'post_init_hook': 'create_missing_journal_for_acquirers',
    'images': ['static/description/banner.png'],
}
