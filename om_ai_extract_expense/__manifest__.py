{
    'name': 'AI Expense Receipts - Read Receipts with Your Own AI',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Read expense receipts with your own AI model: merchant, date, total, currency, taxes and expense '
               'category filled on the draft expense, with confidence and flags, never submitted automatically',
    'description': """
Reads the receipt attached to a draft expense with the AI engine: the merchant, the date, the total, the currency,
the taxes and the expense category are filled for the employee to check before submitting. Photos are read by a
vision model, PDFs from their text.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai_extract', 'hr_expense'],
    'data': [
        'data/hr_expense_data.xml',
        'views/res_config_settings_views.xml',
        'views/hr_expense_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
}
