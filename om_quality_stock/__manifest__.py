{
    'name': 'Quality - Inventory',
    'version': '20.0.1.0.0',
    'category': 'Supply Chain/Quality',
    'summary': 'Quality checks on receipts, deliveries and internal transfers: blocking validation, '
               'quarantine location, lots on hold kept out of reservation, scrap, return to vendor '
               'and certificate of analysis',
    'description': """
Quality checks on transfers: control points on receipts, deliveries and internal transfers create
their checks when the transfer is confirmed, or once per lot when lots are set. A blocking check
holds the validation until it passes or a quality manager overrides it. A failed check moves the
goods to the quarantine location of the warehouse, scraps them, returns them to the vendor or asks
for a retest; its lot is put on hold and kept out of reservation. Deliveries print a certificate of
analysis with the passed checks and their measures.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_quality', 'stock'],
    'data': [
        'views/om_quality_point_views.xml',
        'views/om_quality_check_views.xml',
        'views/om_quality_alert_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_lot_views.xml',
        'views/stock_warehouse_views.xml',
        'views/res_config_settings_views.xml',
        'report/certificate_report.xml',
    ],
    'demo': ['demo/om_quality_stock_demo.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'application': False,
}
