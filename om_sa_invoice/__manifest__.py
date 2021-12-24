# -*- encoding: utf-8 -*-

{
    'name': 'KSA E-Invoicing | Zatca Invoicing',
    'version': '2.0.0',
    'author': 'Odoo Mates, Odoo SA',
    'category': 'Accounting/Localizations',
    'license': 'LGPL-3',
    'summary': """Invoices for the Kingdom of Saudi Arabia""",
    'description': """Electronic invoice KSA - POS Encoded | qrcode | ZATCA | vat | e-invoice | tax | Zakat""",
    'depends': ['l10n_sa', 'om_gcc_invoice'],
    'data': [
        'views/view_move_form.xml',
        'views/report_invoice.xml',
    ],
    'images': ['static/description/banner.png'],
    'live_test_url': 'https://www.youtube.com/watch?v=cTE4T31qhvo&t=1s'
}
