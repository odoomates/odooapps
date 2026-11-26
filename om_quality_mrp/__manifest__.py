{
    'name': 'Quality - Manufacturing',
    'version': '20.0.1.0.0',
    'category': 'Supply Chain/Quality',
    'summary': 'Quality checks in manufacturing: per manufacturing order, per work order step and per '
               'finished lot or serial number, blocking Produce until they pass, scrap or rework '
               'from a failed check',
    'description': """
Quality checks in manufacturing: control points on manufacturing orders, on operations and work
centres create their checks when the order is confirmed: one per order, one per work order step,
or one per finished lot or serial number at production. A blocking check holds Produce and the
end of its work order until it passes or a quality manager overrides it. A failed check raises a
non-conformance, puts the finished lot on hold, and offers scrap or rework.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_quality_stock', 'mrp'],
    'data': [
        'views/om_quality_point_views.xml',
        'views/om_quality_check_views.xml',
        'views/om_quality_alert_views.xml',
        'views/mrp_production_views.xml',
        'views/mrp_workorder_views.xml',
    ],
    'demo': ['demo/om_quality_mrp_demo.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': True,
    'application': False,
}
