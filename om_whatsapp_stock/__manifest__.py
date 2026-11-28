{
    'name': 'WhatsApp Delivery Notifications',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Tell customers by WhatsApp when their order ships or is out for delivery, with the carrier '
               'tracking link, automatically per operation type',
    'description': 'Bridge between Inventory and the WhatsApp connector of Odoo Mates: ready WhatsApp templates and a '
                   'Send by WhatsApp button on transfers; a delivery that is done can go to the customer by WhatsApp '
                   'automatically, once, as set on each operation type, with the tracking number and link of the '
                   'carrier when there is one.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['stock', 'om_whatsapp_base'],
    'data': [
        'data/om_whatsapp_template_data.xml',
        'views/stock_picking_views.xml',
        'views/stock_picking_type_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [
        'data/om_whatsapp_stock_demo.xml',
    ],
    'installable': True,
    'auto_install': True,
}
