{
    'name': 'Sales Commissions',
    'version': '20.0.1.0.0',
    'category': 'Sales/Commissions',
    'summary': 'Sales commissions for salespersons, sales teams and resellers: commission plans and rules, '
               'targets with achievement tiers, team splits, commission statements, approval, '
               'vendor bills, clawback, achievement dashboard and portal',
    'description': 'Commission plans for salespersons, sales teams and resellers: percentage of revenue or margin, '
                   'fixed amount per unit, targets with achievement tiers and caps, commission lines from invoices '
                   'or sales orders, statements approved by the sales manager and paid with a vendor bill.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['sale_management', 'account'],
    'data': [
        'security/ir.access.csv',
        'data/commission_data.xml',
        'data/ir_cron_data.xml',
        'data/portal_entry_data.xml',
        'wizard/commission_compute_wizard_views.xml',
        'wizard/commission_statement_wizard_views.xml',
        'views/commission_plan_views.xml',
        'views/commission_grade_views.xml',
        'views/commission_line_views.xml',
        'views/commission_achievement_views.xml',
        'views/commission_statement_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/commission_menus.xml',
        'views/portal_templates.xml',
        'report/commission_statement_report.xml',
    ],
    'demo': [
        'demo/commission_demo.xml',
    ],
    'installable': True,
    'application': True,
}
