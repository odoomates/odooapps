{
    'name': 'Odoo Mates Academy: Odoo Development',
    'version': '0.1.0',
    'author': 'Odoo Mates',
    'category': 'Tools',
    'summary': 'Learn Odoo development step by step, made for beginners: build your first app, '
               'in your editor or live',
    'description': 'A module to learn with: new to coding? Try it out. Learn Odoo development inside '
                   'Odoo: pick a course and build a real app step by step, writing the code in your '
                   'editor or building it live in the database.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'base_import_module'],
    'data': [
        'security/ir.access.csv',
        'views/academy_views.xml',
        'report/academy_certificate.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_academy/static/src/**/*',
        ],
    },
    'application': True,
    'images': ['static/description/banner.gif'],
}
