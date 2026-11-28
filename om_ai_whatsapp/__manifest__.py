{
    'name': 'WhatsApp AI Sales Assistant',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'AI sales assistant on WhatsApp: answers product, price and stock questions, builds quotations, '
               'sends the quotation PDF and an online payment link, order and delivery status, invoices after '
               'an optional email code, hand-over to a salesperson, working hours, opt-out, reports',
    'description': """
Customers chat with your WhatsApp number and an AI assistant answers from live Odoo data:
products, prices of their price list, stock, quotations built line by line, delivery methods,
the quotation PDF with an online payment link (the order confirms when it is paid), order and
delivery status, and invoices, optionally after a code sent to the customer's email. A person takes
over at any time from Discuss. Works with every WhatsApp provider of the WhatsApp Connector Base.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai', 'om_whatsapp_base', 'sale', 'delivery', 'resource'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/om_ai_whatsapp_data.xml',
        'data/om_ai_tool_data.xml',
        'data/om_ai_prompt_data.xml',
        'data/mail_template_data.xml',
        'views/om_ai_tool_views.xml',
        'views/om_whatsapp_account_views.xml',
        'views/om_ai_whatsapp_conversation_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'report/om_ai_whatsapp_report_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_ai_whatsapp/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
