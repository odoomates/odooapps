{
    'name': 'Odoo 20 Vendor Bill OCR',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Read the uploaded vendor bills: vendor, number, dates, totals, taxes and lines, from PDFs, '
               'scans and photos, on your own server and for free',
    'description': """
Upload a vendor bill, or receive it by email, and the draft bill is filled from it: the vendor recognized by its tax
number, bank account, email or name, the bill number, the bill and due dates, the currency, the taxes and the total,
and the lines of its table when they add up. Everything is read on your own server: the text of the PDFs, and the
scans and the photos with Tesseract. Each bill posted teaches the module where the vendor prints its fields and how
its bills are booked.
    """,
    'sequence': '1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'license': 'LGPL-3',
    'support': 'odoomates@gmail.com',
    'depends': ['account'],
    'external_dependencies': {'python': ['pypdf']},
    'data': [
        'security/ir.access.csv',
        'views/account_move_views.xml',
        'views/bill_ocr_profile_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.gif'],
}
