{
    'name': 'WhatsApp Connector QR',
    'version': '17.0.1.0.0',
    'author': 'Odoo Mates',
    'category': 'Marketing',
    'description': 'Link your WhatsApp to Odoo with a QR code, as a linked device, and send and receive from the server, '
                   'without a browser open: with the WhatsApp Bridge of the module, on your server.',
    'summary': 'Set up the bridge, scan the QR from your phone, and send WhatsApp from Odoo',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_whatsapp_base'],
    'data': [
        'data/ir_cron.xml',
        'views/om_whatsapp_account_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_whatsapp_device/static/src/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
}
