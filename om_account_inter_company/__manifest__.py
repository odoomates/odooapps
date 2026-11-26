{
    'name': 'Inter-Company Invoices and Bills',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Inter-company for groups of companies in one database: a customer invoice of one company '
               'becomes the vendor bill of the other, credit notes as refunds, account, tax, product and '
               'currency mapping, linked documents, inter-company balances with their differences',
    'description': 'Rules per pair of group companies mirror customer invoices and credit notes as vendor bills '
                   'and refunds (and vendor bills as customer invoices), in draft or posted, created as an '
                   'inter-company user, with the invoice PDF attached. A report shows what each group company '
                   'owes the others, as both sides see it, and the differences.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['account', 'om_report_engine'],
    'data': [
        'security/ir.access.csv',
        'views/om_inter_company_rule_views.xml',
        'views/account_move_views.xml',
        'views/account_account_views.xml',
        'views/res_partner_views.xml',
        'views/menu.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
