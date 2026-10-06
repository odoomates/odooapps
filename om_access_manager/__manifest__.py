{
    'name': 'User Access Manager',
    'version': '0.9.10',
    'author': 'Odoo Mates',
    'category': 'Tools',
    'description': 'Decide what each group of users sees and does: apps and menus, data and records, fields, buttons, reports, actions, and when and from where they sign in. Beta.',
    'summary': 'Access Profiles, Hide Menus, Hide Fields, Hide Buttons, Record Rules, Read Only User, Allowed Journals and Warehouses, Login Hours, IP Restriction',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail', 'om_user_audit'],
    'data': [
        'security/om_access_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'wizard/om_access_wizard_views.xml',
        'views/om_access_profile_views.xml',
        'views/res_users_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_access_manager/static/src/**/*',
        ],
        'web.assets_tests': [
            'om_access_manager/static/tests/tours/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
}
