{
    'name': 'Inventory Reports - Valuation',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Inventory valuation report on screen and stock values in the inventory reports: valuation at date, '
               'value of dead and old stock, ABC analysis by cost, export to PDF and Excel',
    'description': 'Adds the stock value to the Inventory Reports and a Stock Valuation report at any date.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_inventory_reports', 'stock_account'],
    'data': [
        'views/menu.xml',
    ],
    'auto_install': True,
    'installable': True,
    'application': False,
}
