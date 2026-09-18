{
    'name': 'Odoo 20 Cheque Printing',
    'version': '1.1.0',
    'category': 'Accounting',
    'summary': 'Configurable cheque formats for printing the cheques of any bank in Odoo 20 Community',
    'description': """
Print vendor payments on the cheques of your bank: each bank journal has its cheque format, with the paper
size and the position of the date, payee, amount, amount in words and the other fields in millimetres,
optional payment stubs and a test print to calibrate the positions on a real cheque.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account_check_printing'],
    'data': [
        'security/ir.access.csv',
        'report/report_check.xml',
        'data/check_format_data.xml',
        'views/check_format_views.xml',
        'views/account_journal_views.xml',
    ],
    'images': ['static/description/icon.png'],
}
