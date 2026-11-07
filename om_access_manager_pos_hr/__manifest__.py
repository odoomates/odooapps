{
    'name': 'User Access Manager for Point of Sale Employees',
    'version': '0.1.0',
    'author': 'Odoo Mates',
    'category': 'Sales/Point of Sale',
    'summary': 'The Point of Sale restrictions of an access profile, for the employees who log in to the shop',
    'description': 'Completely free. Lists POS employees on an access profile: when one of them logs in to the '
                   'shop, the Point of Sale restrictions of the profile apply to them.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_access_manager_pos', 'om_pos_access_hr'],
    'data': [
        'views/om_access_profile_views.xml',
    ],
    'auto_install': True,
}
