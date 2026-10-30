{
    'name': 'User Access Manager',
    'version': '0.11.0',
    'author': 'Odoo Mates',
    'category': 'Tools',
    'description': 'Completely free. Decide what each group of users sees and does: apps and menus, '
                   'data and records, fields, buttons, reports, actions, and when and from where they '
                   'sign in. Feedback is welcome and makes it better. Upgrading Odoo: keep the module '
                   'installed, upgrade a copy of your database first, run the Health Check, set again '
                   'what it lists, and go live.',
    'summary': 'Free Access Manager: Access Profiles, Hide Menus, Hide Fields, Hide Buttons, Record Rules, '
               'Read Only User, Allowed Journals and Warehouses, Login Hours, IP Restriction, Preview as User',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'live_test_url': 'https://www.youtube.com/watch?v=0RubHfvZWoM',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'mail', 'rpc', 'om_user_audit'],
    'data': [
        'security/om_access_security.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'data/om_access_version_data.xml',
        'wizard/om_access_wizard_views.xml',
        'views/om_access_profile_views.xml',
        'views/om_access_health_views.xml',
        'views/om_access_version_views.xml',
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
    'uninstall_hook': 'uninstall_hook',
}
