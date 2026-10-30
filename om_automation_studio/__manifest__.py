{
    'name': 'Automation Studio',
    'version': '0.1.0',
    'author': 'Odoo Mates',
    'category': 'Productivity',
    'description': 'Draw an automation as a flowchart and let it run on your records: conditions, waits, '
                   'approvals, emails, activities and record updates, without code. Follow every record '
                   'on the chart, step by step.',
    'summary': 'Automation Studio, Workflow Automation, Workflow Designer, Flowchart Builder, Approvals, Follow-ups, '
               'Reminders, No-Code Automation, Business Workflow',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'live_test_url': 'https://www.youtube.com/watch?v=hD0A9-cpaWw',
    'license': 'LGPL-3',
    'images': ['static/description/banner.gif'],
    'depends': ['base_automation', 'web'],
    'data': [
        'security/om_automation_studio_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/om_workflow_views.xml',
        'views/om_workflow_run_views.xml',
        'views/om_workflow_approval_views.xml',
        'views/om_workflow_template_views.xml',
        'wizard/om_workflow_template_import_views.xml',
        'views/om_automation_studio_menus.xml',
    ],
    'demo': [
        'demo/om_workflow_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_automation_studio/static/src/**/*',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'application': True,
}
