# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo 15 Recurring Payment',
    'author': 'Odoo Mates',
    'category': 'Accounting',
    'version': '15.0',
    'description': """Use recurring payments to handle periodically repeated payments""",
    'summary': 'Odoo 15 Recurring Payment',
    'sequence': 11,
    'website': 'https://www.odoomates.tech',
    'depends': ['account'],
    'license': 'LGPL-3',
    'data': [
        'data/sequence.xml',
        'data/recurring_cron.xml',
        'security/ir.model.access.csv',
        'views/recurring_template_view.xml',
        'views/recurring_payment_view.xml'
    ],
}
