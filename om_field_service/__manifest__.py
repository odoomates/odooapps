{
    'name': 'Field Service',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'sequence': 56,
    'summary': 'Field service for technicians on site: jobs with site address and equipment, job types '
               'with checklists, planning on a Gantt with free technician suggestions and conflicts, '
               'dispatch map, technician phone screen with navigation, travel and work timers writing '
               'timesheets, checklist, photos, customer signature and a job report emailed to the customer',
    'description': 'Jobs at the customer site on projects and timesheets: planned on the planning Gantt, '
                   'dispatched on a map, run from the phone of the technician (navigation, timers, '
                   'checklist, photos, signature) and closed with a job report sent to the customer.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['project', 'hr_timesheet', 'om_planning_hr', 'base_geolocalize'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/om_field_service_data.xml',
        'report/om_field_service_report.xml',
        'data/mail_template_data.xml',
        'data/portal_entry_data.xml',
        'wizard/om_fs_plan_wizard_views.xml',
        'views/om_fs_job_type_views.xml',
        'views/project_task_views.xml',
        'views/project_project_views.xml',
        'views/om_planning_slot_views.xml',
        'views/hr_employee_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/om_field_service_menus.xml',
        'views/portal_templates.xml',
    ],
    'demo': [
        'demo/om_field_service_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_field_service/static/src/technician/**/*',
            'om_field_service/static/src/map/**/*',
        ],
        'web.assets_backend_lazy': [
            'om_field_service/static/src/dispatch/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
