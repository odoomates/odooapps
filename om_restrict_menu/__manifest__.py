{
    'name': 'Hide Menus by User and Company',
    'version': '1.0',
    'author': 'Odoo Mates',
    'category': 'Tools',
    'description': 'Hide any menu or app for a user, or for everyone while a company is the current company.',
    'summary': 'Hide Menu, Hide Menu for User, Hide Menu by Company, Hide Apps, Hide Submenu, Restrict Menu',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'views/ir_ui_menu_views.xml',
        'views/res_users_views.xml',
        'views/res_company_views.xml',
        'views/menu.xml',
    ],
    'images': ['static/description/banner.gif'],
}
