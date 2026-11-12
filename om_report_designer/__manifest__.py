{
    'name': 'Report Designer',
    'version': '1.0',
    'author': 'Odoo Mates',
    'category': 'Productivity',
    'description': 'Design PDF reports on a page: drag fields, move and resize them, add tables of lines, '
                   'then print from the Print menu or run on screen.',
    'summary': 'Report Designer, Report Builder, Drag and Drop Reports, Custom PDF Reports, Print Layout',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'security/om_report_designer_groups.xml',
        'security/ir.access.csv',
        'views/om_report_design_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/om_report_design_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_report_designer/static/src/report/report_layout.scss',
            'om_report_designer/static/src/designer/*',
            'om_report_designer/static/src/viewer/*',
        ],
        'web.report_assets_common': [
            'om_report_designer/static/src/report/report_layout.scss',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'application': True,
}
