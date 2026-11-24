{
    'name': 'Helpdesk',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'sequence': 45,
    'summary': 'Helpdesk and customer support tickets: teams, email alias, automatic assignment, SLA policies, '
               'customer portal, ratings, canned responses, merge tickets and reports',
    'description': """
Helpdesk app for customer support: tickets created from the email alias of each team or by your
agents, assigned by hand, to the agent with the fewest open tickets or in turn, tracked through
stages, with SLA deadlines in working hours, emails to the customer on each stage, customer ratings
when a ticket is closed, a customer portal to follow, answer and close tickets, merging of tickets,
and ticket and SLA analysis.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail', 'portal', 'rating', 'resource'],
    'data': [
        'security/helpdesk_security.xml',
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_message_subtype_data.xml',
        'data/mail_template_data.xml',
        'data/helpdesk_data.xml',
        'data/portal_entry_data.xml',
        'views/helpdesk_ticket_views.xml',
        'views/helpdesk_team_views.xml',
        'views/helpdesk_stage_views.xml',
        'views/helpdesk_sla_views.xml',
        'views/helpdesk_config_views.xml',
        'views/res_partner_views.xml',
        'report/helpdesk_ticket_report_views.xml',
        'views/helpdesk_portal_templates.xml',
        'wizard/helpdesk_ticket_merge_views.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/helpdesk_demo.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': True,
}
