{
    'name': 'AI Document Reading - Bills, Statements, Receipts and CVs',
    'version': '20.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Read documents with your own AI model: bank statements from PDFs and images into statement '
               'lines, and with the bridges vendor bills, expense receipts and CVs, checked in code and shown for '
               'review, never posted automatically',
    'description': """
Document reading for Odoo on the AI engine, with your own provider or a local model. PDFs are read from their text,
scans and photos by a vision model. Every answer follows a JSON schema that is checked in code, comes with a
confidence and flags, and is shown for review: nothing is posted automatically. This module reads bank statements
into statement lines; its bridges read vendor bills (with Vendor Bill OCR), expense receipts and CVs.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai', 'account'],
    'external_dependencies': {'python': ['pypdf']},
    'data': [
        'security/ir.access.csv',
        'wizard/om_ai_extract_statement_views.xml',
    ],
    'installable': True,
    'application': False,
}
