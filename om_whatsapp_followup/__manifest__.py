{
    'name': 'WhatsApp Payment Follow-ups',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'WhatsApp as an action of the payment follow-up levels: the amount due, the overdue invoices '
               'and their payment links, sent with the email and the letter of the level',
    'description': 'Bridge between the Customer Follow Up Management of Odoo Mates and its WhatsApp connector: each '
                   'follow-up level can send a WhatsApp message with the amount overdue and the list of overdue '
                   'invoices with their online payment links, along with its other actions, by hand or from the '
                   'daily automatic follow-ups. Every message is kept in the chatter of the customer.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_account_followup', 'om_whatsapp_base'],
    'data': [
        'data/om_whatsapp_template_data.xml',
        'views/followup_views.xml',
        'views/followup_send_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
