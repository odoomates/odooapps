{
    'name': 'Customer Credit Limit on Sales Orders',
    'version': '1.0.0',
    'category': 'Sales',
    'summary': 'Block Sales Orders Over the Credit Limit, Credit Limit Override on Sales Orders',
    'description': """
Bridge between the credit limit and Sales: refuse to confirm a sales order that brings the customer over the credit
limit, as an option. Online payments and portal signatures are not blocked.
    """,
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['om_credit_limit', 'sale'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
}
