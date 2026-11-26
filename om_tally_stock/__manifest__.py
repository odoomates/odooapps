{
    'name': 'Tally Connector Inventory',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Import from Tally: units, stock groups and categories, stock items as products, godowns as '
               'locations, batches as lots, opening stock at the value of Tally',
    'description': 'Brings the inventory masters of a Tally company into Odoo: units, product categories, products '
                   'matched by part number, name or HSN, godowns as locations, batches as lots, and the opening '
                   'stock per godown and batch, valued at the rate of Tally. Invoices made from Tally vouchers get '
                   'their products.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_tally_account', 'stock_account'],
    'data': [
        'views/om_tally_import_views.xml',
    ],
    'installable': True,
    'application': False,
}
