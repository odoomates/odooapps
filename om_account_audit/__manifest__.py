{
    'name': 'Odoo 20 Accounting Audit',
    'version': '20.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Data inalterability check, history of the integrity checks, entries secured on period closing '
               'and an audit pack for the auditors',
    'description': 'Brings the inalterability features of Odoo 20 Community within reach: the data inalterability '
                   'check and the securing of the entries from the Review menu, a weekly integrity check kept in a '
                   'history, the entries secured when a period is closed, and an audit pack in PDF for a period.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['om_account_accountant'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'views/account_integrity_check_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/audit_pack_views.xml',
        'report/audit_pack_report.xml',
        'report/audit_pack_templates.xml',
        'views/menu.xml',
    ],
    'installable': True,
}
