{
    'name': 'WhatsApp Connector Web',
    'version': '1.0',
    'author': 'Odoo Mates',
    'category': 'Marketing',
    'description': 'Send WhatsApp messages and PDFs from Odoo through WhatsApp Web, open in another tab, with the Odoo Mates browser extension.',
    'summary': 'WhatsApp Web, Send WhatsApp from Odoo, WhatsApp PDF, WhatsApp Invoice, WhatsApp without API',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_whatsapp_base'],
    'data': [
        'views/om_whatsapp_account_views.xml',
    ],
    'demo': [
        'demo/om_whatsapp_web_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_whatsapp_web/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'om_whatsapp_web/static/tests/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
}
