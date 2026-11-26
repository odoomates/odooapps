{
    'name': 'Tally Connector - Import from Tally',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Import from Tally, TallyPrime to Odoo, Tally migration: chart of accounts, ledgers, parties, '
               'opening balances with open bills, vouchers, invoices, stock items, godowns, opening stock',
    'description': 'Moves a Tally company into Odoo: upload the XML export of Tally or connect to Tally directly, '
                   'review the analysis, map groups, ledgers, parties and stock items, check the trial balance, '
                   'then import the opening balances or the full voucher history. Installs the base, accounting '
                   'and inventory parts together.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_tally_base', 'om_tally_account', 'om_tally_stock'],
    'data': [],
    'installable': True,
    'application': True,
}
