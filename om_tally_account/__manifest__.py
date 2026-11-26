{
    'name': 'Tally Connector Accounting',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Import from Tally: chart of accounts mapping, parties, journals, taxes, cost centres, opening '
               'balances with open bills, full voucher history, trial balance check',
    'description': 'Brings the accounting of a Tally company into Odoo: maps the groups and ledgers of Tally to the '
                   'chart of accounts, links or creates the parties, journals and analytic accounts, posts the '
                   'opening balances with one line per open bill, imports the vouchers as journal entries or as '
                   'invoices, bills and payments, and checks the trial balance before posting.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_tally_base', 'account'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/om_tally_import_views.xml',
    ],
    'installable': True,
    'application': False,
}
