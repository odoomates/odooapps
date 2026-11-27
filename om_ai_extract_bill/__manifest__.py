{
    'name': 'AI Vendor Bill Reading - Bill OCR with Your Own AI',
    'version': '20.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Read vendor bills with your own AI model in Vendor Bill OCR: an AI engine next to the reading on '
               'your server, for PDFs, scans and photos, with confidence and flags, never posted automatically',
    'description': """
Adds an AI engine to Vendor Bill OCR. Choose in the settings whether the bills are read on your server or by your
AI model (vision for scans and photos). The vendor is still recognized by its tax number, bank account, email or
name, the taxes and the accounts still come from what earlier bills taught, and the bill stays a draft to check.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai_extract', 'om_account_bill_ocr'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
}
