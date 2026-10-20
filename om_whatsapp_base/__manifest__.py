{
    'name': 'WhatsApp Connector Base',
    'version': '1.0',
    'author': 'Odoo Mates',
    'category': 'Marketing',
    'description': 'WhatsApp templates, composer and message log for any document, ready for any WhatsApp provider.',
    'summary': 'WhatsApp, WhatsApp Templates, Send WhatsApp, WhatsApp Message Log, Click to Chat',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail', 'phone_validation'],
    'data': [
        'security/om_whatsapp_groups.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'wizard/om_whatsapp_composer_views.xml',
        'views/om_whatsapp_account_views.xml',
        'views/om_whatsapp_template_views.xml',
        'views/om_whatsapp_message_views.xml',
        'views/res_partner_views.xml',
        'views/ir_actions_server_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_whatsapp_base/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'om_whatsapp_base/static/tests/**/*',
        ],
    },
    'demo': [
        'demo/om_whatsapp_demo.xml',
    ],
    'application': True,
    'images': ['static/description/banner.gif'],
}
