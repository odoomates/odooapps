# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    'name': 'Customer Vendor Statement',
    'version': '11.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Customer- Vendor Statement by Currency',
    'sequence': '10',
    'description': 'Open any customer or vendor form and click on action--> Customer / Vendor Statement',
    "author": "Odoo Mates, Abdallah Mohamed",
    'website': '',
    'support': 'odoomates@gmail.com',
    'depends': [
        'account',
    ],
    'data': [
        'views/statement.xml',
        'wizard/customer_vendor_statement_wizard.xml',
    ],
    'installable': True,
    'application': False,
}
