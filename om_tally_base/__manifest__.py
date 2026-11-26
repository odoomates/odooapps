{
    'name': 'Tally Connector Base',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Read Tally data into Odoo: XML export upload, direct connection to Tally, reading in the '
               'background, staging of masters and vouchers, analysis report',
    'description': 'The engine of Import from Tally: reads the masters and vouchers of a Tally company from its XML '
                   'export or from Tally itself over its HTTP port, keeps them in staging tables, '
                   'and shows an analysis before anything is imported.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['mail'],
    'data': [
        'security/om_tally_groups.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/om_tally_import_views.xml',
        'views/om_tally_data_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/om_tally_demo.xml',
    ],
    'installable': True,
    'application': False,
}
