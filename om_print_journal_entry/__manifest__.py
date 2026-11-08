{
    'name': 'Print Journal Entries',
    'version': '14.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Print Journal Entry, Journal Entries PDF, Print Accounting Entries, Journal Voucher Print, '
               'Print Journal Items, Journal Entry Report',
    'description': 'Print any journal entry, invoice or bill as a PDF with its lines, debit and credit.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'report/report.xml',
        'report/report_journal_entries.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
}
