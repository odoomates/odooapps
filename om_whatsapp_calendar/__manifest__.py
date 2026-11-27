{
    'name': 'WhatsApp Meeting Reminders',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Calendar',
    'summary': 'WhatsApp as a reminder type of the calendar: each attendee gets the reminder of the meeting on '
               'WhatsApp, at their own time zone',
    'description': 'Bridge between Calendar and the WhatsApp connector of Odoo Mates: a calendar reminder of type '
                   'WhatsApp sends each attendee who has not declined a WhatsApp message before the meeting, from a '
                   'template you can edit. Opted-out numbers are skipped, and every message is kept on the meeting.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['calendar', 'om_whatsapp_base'],
    'data': [
        'data/om_whatsapp_template_data.xml',
        'views/calendar_alarm_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
