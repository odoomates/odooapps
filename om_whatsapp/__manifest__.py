{
    'name': 'WhatsApp Connector Meta',
    'version': '1.0',
    'author': 'Odoo Mates',
    'category': 'Marketing',
    'description': 'Send and receive WhatsApp messages in Odoo through the official WhatsApp Cloud API of Meta: '
                   'templates with PDFs, automation rules, conversations in Discuss, from the server.',
    'summary': 'WhatsApp Cloud API, Meta WhatsApp, WhatsApp Business API, WhatsApp Automation, WhatsApp Invoice',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_whatsapp_base'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'wizard/om_whatsapp_meta_setup_views.xml',
        'wizard/om_whatsapp_composer_views.xml',
        'views/om_whatsapp_account_views.xml',
        'views/om_whatsapp_template_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_whatsapp/static/src/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
}
