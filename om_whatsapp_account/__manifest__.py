{
    'name': 'WhatsApp Invoices and Payments',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Send invoices, credit notes and payment receipts by WhatsApp, with the PDF and the online '
               'payment link, by hand or automatically',
    'description': 'Bridge between Invoicing and the WhatsApp connector of Odoo Mates: ready WhatsApp templates and '
                   'a Send by WhatsApp button on customer invoices, credit notes and payments, the PDF attached and '
                   'the link to view and pay the invoice online, and optional automatic sending when an invoice is '
                   'posted or a payment confirmed.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['account', 'om_whatsapp_base'],
    'data': [
        'data/om_whatsapp_template_data.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
