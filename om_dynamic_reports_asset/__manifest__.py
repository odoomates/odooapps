{
    'name': 'Dynamic Accounting Reports - Assets and Deferrals',
    'version': '17.0.1.0.1',
    'category': 'Accounting/Accounting',
    'summary': 'Depreciation Schedule, Deferred Revenue and Deferred Expense in the dynamic accounting reports, '
               'from Assets Management',
    'description': 'Bridge between Dynamic Accounting Reports and Assets Management: the recognition schedule of '
                   'the deferred revenues and the prepaid expenses, month by month.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.gif'],
    'depends': ['om_dynamic_reports', 'om_account_asset'],
    'data': [
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
}
