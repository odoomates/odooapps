{
    'name': 'Odoo 20 Bank Statement Import',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Import the bank statements of your bank: CAMT, MT940, OFX, QIF, CSV and Excel',
    'description': """
Import the statements your bank gives you, in the format it offers: CAMT.053 (ISO 20022), MT940 (SWIFT), OFX or
QFX, QIF, and CSV or Excel with a map of the columns of your bank, which is kept for the next import.

The journal is recognised from the account number in the file, the transactions already imported are skipped, and
the file stays attached to the statement. The statements are then reconciled as usual.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account'],
    'data': [
        'security/ir.access.csv',
        'views/account_statement_import_map_views.xml',
        'wizard/account_statement_import_views.xml',
        'views/account_journal_views.xml',
        'views/account_bank_statement_views.xml',
    ],
    'images': ['static/description/statement_import.png'],
}
