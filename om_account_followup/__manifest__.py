# -*- coding: utf-8 -*-

{
    'name': 'Customer Follow Up Management',
    'version': '14.0.5.0.1',
    'category': 'Accounting',
    'description': """Customer FollowUp Management""",
    'summary': """Customer FollowUp Management""",
    'author': 'Odoo Mates, Odoo S.A',
    'license': 'LGPL-3',
    'website': '',
    'depends': ['account', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'wizard/followup_print_view.xml',
        'wizard/followup_results_view.xml',
        'views/followup_view.xml',
        'views/account_move.xml',
        'views/partners.xml',
        'views/report_followup.xml',
        'views/reports.xml',
        'views/followup_partner_view.xml',
        'report/followup_report.xml',
    ],
    'demo': ['demo/demo.xml'],
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
}

