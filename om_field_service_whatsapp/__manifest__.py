{
    'name': 'Field Service - WhatsApp',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'summary': 'WhatsApp messages to the customer of a field service job: job planned, technician on the '
               'way, job done with the report, from WhatsApp templates you can edit',
    'description': 'Bridge between Field Service and the WhatsApp connector of Odoo Mates: the customer gets a '
                   'WhatsApp message when the job is planned, when the technician starts travelling and when the '
                   'job is done, with the job report.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_field_service', 'om_whatsapp_base'],
    'data': [
        'data/om_whatsapp_template_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
