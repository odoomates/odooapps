{
    'name': 'Inventory Reports',
    'version': '20.0.1.1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Inventory reports on screen with filters, export to PDF and Excel: stock on hand, stock at date, '
               'stock card, product ledger, inventory summary, negative stock, stock ageing, slow moving, '
               'dead stock, ABC analysis, stock turnover, FSN analysis, stock-out forecast, overstock, '
               'reorder report, warehouse stock',
    'description': 'Inventory reports on screen: filters at the top, groups that unfold, drill-down to the moves, '
                   'saved views, and export to PDF, Excel and CSV.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.gif'],
    'depends': ['stock', 'om_report_engine'],
    'data': [
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
