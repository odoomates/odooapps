{
    'name': 'Flow Visualizer',
    'version': '0.1.0',
    'author': 'Odoo Mates',
    'category': 'Technical',
    'description': 'See what a click does behind the screen: the records a button creates, edits and deletes, '
                   'as a tree of the methods that made them, each one a click away.',
    'summary': 'Data Flow, Record Trace, What Happened, Created Records, Business Flow Tree, Developer Tool',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'flow_visualizer/static/src/**/*',
        ],
    },
}
