{
    'name': 'Odoo 20 Assets Dashboard',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Assets dashboard in the Dashboards app: gross value, depreciation and book value of the assets',
    'description': """
The Assets dashboard of the Finance section: the gross value, the accumulated depreciation and
the book value of the running assets, and the depreciation posted and to post by month and by category.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': [
        'om_spreadsheet_account',
        'om_account_asset',
    ],
    'data': [
        'data/dashboards.xml',
    ],
    'auto_install': True,
    'images': ['static/description/icon.png'],
}
