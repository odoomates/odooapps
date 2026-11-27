{
    'name': 'WhatsApp AI Sales Assistant - Shipping Messages',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Shipping messages on WhatsApp: when the delivery of an order taken by the WhatsApp AI assistant is '
               'validated, the customer gets the carrier and the tracking link in their WhatsApp conversation',
    'description': """
When a delivery of an order that came from a WhatsApp AI conversation is validated, the customer
gets a WhatsApp message in that conversation with the carrier and the tracking link, once per
delivery. Works with the carrier connectors that fill the tracking reference.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai_whatsapp', 'stock_delivery'],
    'data': [
        'views/om_whatsapp_account_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
