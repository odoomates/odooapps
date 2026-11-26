{
    'name': 'Planning',
    'version': '20.0.1.0.0',
    'category': 'Services/Planning',
    'summary': 'Plan people, crews, machines, vehicles and rooms on a Gantt chart: shifts, open slots, '
               'roles, templates, rotations, recurring slots, conflicts, publish and send schedules, '
               'claim and switch requests, portal and calendar feed',
    'description': 'A planning engine for any resource: people with or without an employee record, crews, '
                   'equipment, vehicles and rooms, planned on a Gantt chart and shared with the people who '
                   'do the work.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['resource', 'mail', 'portal', 'om_web_gantt'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/mail_template_data.xml',
        'data/portal_entry_data.xml',
        'views/om_planning_slot_views.xml',
        'views/om_planning_role_views.xml',
        'views/om_planning_template_views.xml',
        'views/om_planning_rotation_views.xml',
        'views/om_planning_schedule_views.xml',
        'views/om_planning_request_views.xml',
        'views/resource_resource_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/om_planning_rotation_apply_views.xml',
        'wizard/om_planning_load_views.xml',
        'views/om_planning_menus.xml',
        'views/om_planning_templates.xml',
    ],
    'demo': [
        'demo/om_planning_demo.xml',
    ],
    'assets': {
        'web.assets_backend_lazy': [
            'om_planning/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
