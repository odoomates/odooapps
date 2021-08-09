# -*- coding:utf-8 -*-

{
    'name': 'Sale Product Picker',
    'category': 'Generic Modules/Sales',
    'version': '13.0.1.0.0',
    'sequence': 1,
    'author': 'Odoo Mates, Tecnativa, Odoo Community Association (OCA)',
    'summary': 'Sale Product Picker',
    'license': "AGPL-3",
    'live_test_url': '',
    'description': "Sale Product Picker",
    'website': 'https://www.odoomates.tech',
    'depends': [
        'sale',
        'sale_management',
        'web_widget_one2many_product_picker',
    ],
    'data': [
        'views/sale_order.xml',
    ],
    'images': [],
    'application': False,
}
