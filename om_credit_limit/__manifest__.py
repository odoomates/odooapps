{
    'name': 'Customer Credit Limit With Warning and Blocking',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Customer Credit Limit, Block Invoices Over the Credit Limit, Credit Limit Override, '
               'Block Sales Orders Over the Credit Limit',
    'description': """
Refuse to post a customer invoice that brings the customer over the credit limit. The users allowed to override the
limit can still post it, and the override is logged on the invoice. With Sales installed, the same applies to the
confirmation of a sales order, as an option.
    """,
    'sequence': 11,
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'live_test_url': 'https://www.youtube.com/watch?v=wNhWs29T5Zs',
    'depends': ['account'],
    'data': [
        'security/res_groups.xml',
        'views/res_config_settings_views.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'images': ['static/description/banner.png'],
    'installable': True,
}
