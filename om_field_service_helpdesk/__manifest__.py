{
    'name': 'Field Service - Helpdesk',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'summary': 'Field service jobs from helpdesk tickets: plan an intervention from a ticket with its '
               'customer, site, description and equipment, jobs created by ticket type or team, job status '
               'on the ticket, ticket notified with the job report and closed when the job is done',
    'description': 'Bridge between Helpdesk and Field Service: a ticket that needs a visit on site becomes a '
                   'field service job, and the ticket follows the job until its report.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_field_service', 'om_helpdesk'],
    'data': [
        'views/helpdesk_team_views.xml',
        'views/helpdesk_ticket_type_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/project_task_views.xml',
    ],
    'demo': [
        'demo/om_field_service_helpdesk_demo.xml',
    ],
    'installable': True,
    'auto_install': True,
}
