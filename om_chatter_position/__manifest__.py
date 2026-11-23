{
    'name': 'Odoo Chatter Position',
    'version': '20.0.1.0.1',
    'category': 'Productivity',
    'summary': 'Chatter beside or below the form, Odoo 20 Chatter Position, Chatter Side, Chatter Bottom',
    'description': """
Each user picks where the chatter sits on a form, in My Preferences: Automatic (Odoo's own
choice, beside the form on wide screens and below it on narrow ones), Below the form, or
Beside the form.
""",
    'author': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'depends': ['web', 'mail'],
    'data': [
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_chatter_position/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
}
