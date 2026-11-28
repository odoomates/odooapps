{
    'name': 'Barcode Scanning for Inventory',
    'version': '20.0.1.0.1',
    'category': 'Inventory/Inventory',
    'summary': 'Scan receipts, deliveries, internal transfers and inventory counts on a phone, a tablet '
               'or a handheld scanner: lots, serial numbers, packages, locations, GS1 barcodes, camera '
               'scanning, stock lookup',
    'description': 'A touch screen for the warehouse floor: scan an operation, a transfer, locations, '
                   'products, lots, serial numbers and packages, validate with backorders, count stock '
                   'and look up any barcode.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['stock', 'barcodes', 'barcodes_gs1_nomenclature'],
    'data': [
        'views/om_stock_barcode_menus.xml',
        'views/stock_picking_type_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_stock_barcode/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
