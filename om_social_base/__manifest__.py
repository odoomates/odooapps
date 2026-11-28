{
    'name': 'Social Inbox',
    'version': '1.0.2',
    'author': 'Odoo Mates',
    'category': 'Marketing',
    'description': 'One inbox in Discuss for the chats of your customers: accounts, contacts, conversations, '
                   'message status, receipts and reactions, ready for any messaging channel and provider.',
    'summary': 'Social Inbox, Omnichannel Inbox, Customer Chats, Conversations in Discuss, Messaging Base',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/om_social_groups.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'wizard/om_social_composer_views.xml',
        'views/om_social_account_views.xml',
        'views/om_social_identity_views.xml',
        'views/om_social_message_views.xml',
        'views/res_partner_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_social_base/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'om_social_base/static/tests/**/*',
        ],
    },
    'application': True,
    'images': ['static/description/banner.png'],
}
