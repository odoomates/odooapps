{
    'name': 'User Access Manager for Point of Sale',
    'version': '0.1.0',
    'author': 'Odoo Mates',
    'category': 'Sales/Point of Sale',
    'summary': 'Restrict what each cashier may do in the Point of Sale, per access profile',
    'description': 'Completely free. Adds the Point of Sale restrictions of POS Access Control to the access '
                   'profiles of the User Access Manager: every cashier of a profile gets them.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_access_manager', 'om_pos_access', 'point_of_sale'],
    'data': [
        'views/om_access_profile_views.xml',
    ],
    # installs itself, with POS Access Control, once the Access Manager and the Point of Sale are there
    'auto_install': ['om_access_manager', 'point_of_sale'],
}
