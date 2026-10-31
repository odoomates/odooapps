{
    'name': 'Hide Menus by User and Company',
    'version': '1.1',
    'author': 'Odoo Mates',
    'category': 'Tools',
    'description': 'Hide any menu or app for a user, or for everyone while a company is the current company, '
                   'or show a user only the apps chosen.',
    'summary': 'Hide Menu, Hide Menu for User, Hide Menu by Company, Hide Apps, Hide Submenu, Restrict Menu',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'live_test_url': 'https://www.youtube.com/watch?v=vArtxfp2mLo',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.access.csv',
        'views/ir_ui_menu_views.xml',
        'views/res_users_views.xml',
        'views/res_company_views.xml',
        'views/menu.xml',
        'wizard/om_restrict_menu_set_views.xml',
    ],
    'images': ['static/description/banner.gif'],
}
