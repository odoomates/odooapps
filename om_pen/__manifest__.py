{
    'name': 'Odoo Mates Pen - No Code Customizer',
    'version': '20.0.1.0.5',
    'category': 'Productivity',
    'summary': 'No Code Customizer, Codeless Studio for Odoo Community: App Builder, Form and View '
               'Editor, Custom Fields, Report Designer, Approvals, Automations, Access Rights, Drag and Drop',
    'description': """
A no code customizer for Odoo: a visual, drag and drop Studio, opened from the pen in the top bar.
Codeless customization for Odoo Community.

Form editor and view editor on the real screen: forms, lists, kanban, search, calendar, pivot, graph
and activity views. Add custom fields of any kind, tabs, columns, smart buttons, header buttons,
ribbons, a chatter and stages. No code app builder: new apps with their menus and icon.
Report designer: PDF reports from blocks on a live preview. Put approvals on buttons, create automations, and
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
