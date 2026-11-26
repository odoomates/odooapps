{
    'name': 'Inter-Company Sales and Purchases',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Inter-company sales and purchase orders: a sales order of one group company becomes the '
               'purchase order of the other (and the reverse), quantities and cancellations followed, the '
               'receipt validated with the delivery with the same lots and serial numbers',
    'description': 'Confirming a sales order to another company of the group creates its purchase order there, '
                   'as a request for quotation or confirmed, in the warehouse of the rule; a purchase order to a '
                   'group company creates its sales order. The delivery can validate the receipt of the other '
                   'company, and the invoice of the order becomes the bill of its purchase order.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_account_inter_company', 'sale_stock', 'purchase_stock'],
    'data': [
        'security/ir.access.csv',
        'views/om_inter_company_rule_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
}
