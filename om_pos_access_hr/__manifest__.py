{
    'name': 'POS Access Control for Employees',
    'version': '0.1.1',
    'author': 'Odoo Mates',
    'category': 'Sales/Point of Sale',
    'summary': 'The Point of Sale restrictions of POS Access Control, for the employees who log in to the '
               'shop with a badge or a PIN',
    'description': 'Completely free. Sets the Point of Sale restrictions on each employee who logs in to the shop: '
                   'an employee with rules of their own follows them, the others follow their Odoo user, or else '
                   'the Odoo user who opened the shop.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_pos_access', 'pos_hr'],
    'data': [
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'om_pos_access_hr/static/src/**/*',
        ],
    },
    # installs itself once both are there
    'auto_install': ['om_pos_access', 'pos_hr'],
}
