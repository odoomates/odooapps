{
    'name': 'Approvals',
    'version': '1.1.0',
    'category': 'Productivity',
    'summary': 'Approval flows for any app: a button waits for its approval before it runs, e.g. confirming a '
               'sale order above an amount',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'web', 'rpc'],
    'excludes': ['approvals'],
    'data': [
        'security/om_approval_security.xml',
        'security/ir.access.csv',
        'data/om_approval_data.xml',
        'wizard/approval_dialog_views.xml',
        'wizard/approval_simulate_views.xml',
        'views/om_approval_flow_views.xml',
        'views/om_approval_request_views.xml',
        'views/approval_delegation_views.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/om_approval_demo.xml'],
    'assets': {
        'web.assets_backend': [
            'om_approval/static/src/**/*',
        ],
        'web.assets_tests': [
            'om_approval/static/tests/tours/**/*',
        ],
    },
    'images': ['static/description/banner.gif'],
    'application': True,
}
