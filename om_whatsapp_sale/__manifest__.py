{
    'name': 'WhatsApp Quotations and Orders',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Send quotations and order confirmations by WhatsApp, with the PDF and the link to sign and pay '
               'online, by hand or automatically on confirmation',
    'description': 'Bridge between Sales and the WhatsApp connector of Odoo Mates: ready WhatsApp templates and a '
                   'Send by WhatsApp button on quotations and sales orders, with the PDF and the link to view, sign '
                   'and pay online; the quotation is marked as sent, and the order confirmation can go '
                   'automatically, once, when the order is confirmed (online orders included).',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['sale', 'om_whatsapp_base'],
    'data': [
        'data/om_whatsapp_template_data.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
