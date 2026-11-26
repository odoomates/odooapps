{
    'name': 'Quality',
    'version': '20.0.1.0.0',
    'category': 'Supply Chain/Quality',
    'sequence': 55,
    'summary': 'Quality management: control points, inspection templates, quality checks with measures and '
               'photos, blocking checks with manager override, non-conformances, corrective and preventive '
               'actions, quality teams and a quality dashboard',
    'description': """
Quality management: control points say what to check, where and how often (every time, every Nth,
a random share, once per lot, every X days); checks are recorded on a touch-friendly screen with
pass/fail buttons, measures against limits, photos and notes; a blocking check holds the document
until it passes or a manager overrides it with a reason; failures raise non-conformances with root
cause, cost and corrective and preventive actions, followed by quality teams through their stages.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['product', 'mail', 'uom'],
    'data': [
        'security/om_quality_security.xml',
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'data/om_quality_data.xml',
        'views/om_quality_team_views.xml',
        'views/om_quality_point_views.xml',
        'views/om_quality_template_views.xml',
        'views/om_quality_check_views.xml',
        'views/om_quality_measure_views.xml',
        'views/om_quality_alert_views.xml',
        'views/om_quality_action_views.xml',
        'views/om_quality_config_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/om_quality_override_views.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/om_quality_demo.xml'],
    'assets': {
        'web.assets_backend': [
            'om_quality/static/src/**/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
}
