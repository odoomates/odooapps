{
    'name': 'AI Live Chat Agent - Your Own AI Answers Website Visitors',
    'version': '20.0.1.0.0',
    'category': 'Website/Live Chat',
    'summary': 'An AI agent answers the live chat visitors of your website from your FAQ, texts, website pages '
               'and products, gives live prices and stock, creates leads and helpdesk tickets and hands over to '
               'an operator, with your own AI provider or a local model',
    'description': """
An AI agent for the website live chat, on the AI engine. It answers visitors on the chosen live chat channels from
your knowledge sources (texts, FAQ, website pages, products) found by full-text search or embeddings, looks up
products with their price and stock, creates a lead or a helpdesk ticket when the apps are installed, and hands the
chat over to an operator on request, when it is not sure or within working hours. It never invents a price. Replies
are queued so the visitor never waits on a blocked request, and visitors have rate limits.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai', 'im_livechat', 'website_livechat'],
    'data': [
        'security/ir.access.csv',
        'data/om_ai_livechat_data.xml',
        'views/om_ai_livechat_source_views.xml',
        'views/om_ai_livechat_agent_views.xml',
        'views/om_ai_livechat_job_views.xml',
        'views/im_livechat_channel_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/om_ai_livechat_demo.xml',
    ],
    'installable': True,
    'application': False,
}
