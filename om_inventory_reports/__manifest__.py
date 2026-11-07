{
    'name': 'Inventory Reports',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Inventory reports on screen with filters, export to PDF and Excel: stock on hand, stock at date, '
               'stock card, product ledger, inventory summary, negative stock, stock ageing, slow moving, '
               'dead stock, ABC analysis, stock turnover, reorder report, warehouse stock',
    'description': 'Inventory reports on screen: filters at the top, groups that unfold, drill-down to the moves, '
                   'saved views, and export to PDF, Excel and CSV.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['stock', 'mail'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'report/report_templates.xml',
        'views/report_schedule_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_inventory_reports/static/src/report_action/*',
        ],
    },
    'installable': True,
    'application': False,
}
