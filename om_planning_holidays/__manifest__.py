{
    'name': 'Planning - Time Off',
    'version': '20.0.1.0.0',
    'category': 'Services/Planning',
    'summary': 'Time off in the planning: greyed on the Gantt, conflicts for approved and pending time off, '
               'slots kept, unassigned or flagged when a time off is approved',
    'description': 'Bridge between Planning and Time Off: approved time off blocks the employee on the Gantt, '
                   'and the slots it overlaps are handled by a company policy.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_planning_hr', 'hr_holidays'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
