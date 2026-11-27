{
    'name': 'WhatsApp eCommerce Orders and Abandoned Carts',
    'version': '20.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'WhatsApp confirmation of the online orders and a WhatsApp reminder of the abandoned carts, with '
               'the link back to the cart, sent once',
    'description': 'Bridge between eCommerce and the WhatsApp quotations and orders of Odoo Mates: an online order '
                   'confirmed by its payment is confirmed to the customer by WhatsApp, and a cart left by a signed-in '
                   'customer gets one WhatsApp reminder with the link to resume it. Opted-out numbers are skipped.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['website_sale', 'om_whatsapp_sale'],
    'data': [
        'data/om_whatsapp_template_data.xml',
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
