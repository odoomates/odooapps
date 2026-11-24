{
    'name': 'Gantt View',
    'version': '20.0.1.0.1',
    'category': 'Productivity',
    'summary': 'Gantt view for any model: timeline with drag and drop, resize, group rows, progress, '
               'dependencies, capacity totals and non-working days, a base for planning, rental and '
               'field service apps',
    'description': 'A new "gantt" view type for Odoo Community: records on a timeline by day, week, month or '
                   'year, grouped in rows, moved and resized with the mouse.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['web'],
    'assets': {
        'web.assets_backend_lazy': [
            'om_web_gantt/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
