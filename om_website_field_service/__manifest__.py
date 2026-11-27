{
    'name': 'Website Field Service',
    'version': '20.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Online service request form for field service: customer, site address, equipment and '
               'serial number, description, photos and preferred dates create a job ready to dispatch; '
               'customers follow their jobs, technician and signed report in the portal',
    'description': 'Website and portal for Field Service: customers ask for an intervention on the website and '
                   'follow their jobs in their account, with the planned date, the technician and the signed '
                   'job report.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_field_service', 'website'],
    'data': [
        'data/website_field_service_data.xml',
        'views/project_task_views.xml',
        'views/res_config_settings_views.xml',
        'views/website_field_service_templates.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
}
