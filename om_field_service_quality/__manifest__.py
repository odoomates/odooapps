{
    'name': 'Field Service - Quality',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'summary': 'Quality worksheets on field service jobs: control points per job type (pass/fail, measures '
               'with tolerances, photos, instructions) done on the phone of the technician, non-conformances '
               'on failure, checks in the job report and jobs held until their checks are done',
    'description': 'Bridge between Field Service and Quality: the job types bring their quality control points, '
                   'the technician records the checks on site, failures raise non-conformances on the job and '
                   'the customer equipment, and the results are printed in the job report.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_field_service', 'om_quality'],
    'data': [
        'views/om_quality_point_views.xml',
        'views/om_quality_alert_views.xml',
        'views/om_fs_job_type_views.xml',
        'views/project_task_views.xml',
        'views/res_config_settings_views.xml',
        'report/om_field_service_report.xml',
    ],
    'demo': [
        'demo/om_field_service_quality_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_field_service_quality/static/src/**/*',
        ],
    },
    'installable': True,
    'auto_install': True,
}
