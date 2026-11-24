{
    'name': 'Website Helpdesk',
    'version': '20.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Helpdesk ticket form on your website: a Help page with the teams, a ticket form per team '
               'with attachments, the ticket number on the confirmation page and a link to the portal',
    'description': """
Publish a ticket form for your helpdesk teams on the website. Customers pick a team on the Help page,
fill in their name, email, phone, subject, description and attachments, and get the ticket number and a
link to follow the ticket in their portal. The customer is found or created from the email.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_helpdesk', 'website'],
    'data': [
        'security/ir.access.csv',
        'data/website_helpdesk_data.xml',
        'views/helpdesk_team_views.xml',
        'views/website_helpdesk_templates.xml',
    ],
    'demo': ['data/website_helpdesk_demo.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}
