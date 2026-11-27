{
    'name': 'WhatsApp POS Receipts',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Send the Point of Sale receipt by WhatsApp from the receipt screen: the number next to the '
               'email, the receipt as a picture and the invoice PDF',
    'description': 'Bridge between the Point of Sale and the WhatsApp connector of Odoo Mates: the send receipt '
                   'dialog of the POS gets a WhatsApp number and button; the customer gets the receipt as a picture, '
                   'with the invoice PDF when the order is invoiced (a PDF of both on the Meta Cloud API, at the top of '
                   'the approved template), from a WhatsApp template you can edit. The '
                   'message is kept on the order; opted-out numbers are skipped.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['point_of_sale', 'om_whatsapp_base'],
    'data': [
        'data/om_whatsapp_report.xml',
        'data/om_whatsapp_template_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'om_whatsapp_pos/static/src/**/*',
        ],
    },
    'installable': True,
    'auto_install': True,
}
