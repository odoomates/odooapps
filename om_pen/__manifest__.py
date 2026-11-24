{
    'name': 'Odoo Mates Pen',
    'version': '20.0.1.0.1',
    'category': 'Productivity',
    'summary': 'Studio for Odoo Community, No Code App Builder, View Editor, Report Designer, Approvals, '
               'Automations, Access Rights, Add Fields, Drag and Drop, Odoo 20',
    'description': """
A visual, drag and drop Studio for Odoo, opened from the pen in the top bar.

Edit every view on the real screen: forms, lists, kanban, search, calendar, pivot, graph
and activity views. Add fields of any kind, tabs, columns, smart buttons, header buttons,
ribbons, a chatter and stages. Build new apps with their menus and icon. Design PDF
reports from blocks on a live preview. Put approvals on buttons, create automations, and
manage access rights. Changes are drafts until published, can be undone, are kept as
versions, and everything can be exported as an installable module and imported back.
""",    'sequence': 10,
    'author': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'depends': ['web'],
    'data': [
        'security/security.xml',
        'views/om_pen_views.xml',
        'security/ir.access.csv',
    ],
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_backend': [
            'om_pen/static/src/**/*',
        ],
        'web.assets_tests': [
            'om_pen/static/tests/tours/*.js',
        ],
    },
    'live_test_url': 'https://www.youtube.com/watch?v=i-6JEtXyjXY',
    'license': 'LGPL-3',
    'images': ['static/description/banner.gif'],
}
