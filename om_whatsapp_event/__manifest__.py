{
    'name': 'WhatsApp Event Registrations and Reminders',
    'version': '20.0.1.0.0',
    'category': 'Marketing/Events',
    'summary': 'WhatsApp in the communication of events: registration confirmation and reminders to the '
               'attendees, scheduled like the emails',
    'description': 'Bridge between Events and the WhatsApp connector of Odoo Mates: the communication schedule of an '
                   'event, or of an event template, takes WhatsApp templates next to the email ones, to confirm each '
                   'registration and remind the attendees before the event. Opted-out numbers are skipped, and every '
                   'message is kept on the registration.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['event', 'om_whatsapp_base'],
    'data': [
        'security/ir.access.csv',
        'data/om_whatsapp_template_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_whatsapp_event/static/src/**/*',
        ],
    },
    'installable': True,
    'auto_install': True,
}
