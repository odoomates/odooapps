{
    'name': 'Post-dated Cheques',
    'version': '0.1.1',
    'author': 'Odoo Mates',
    'category': 'Accounting/Accounting',
    'summary': 'Post Dated Cheques, PDC, PDC Received, PDC Issued, Cheque Register, Deposit, Clear and Bounce '
               'Cheques',
    'description': 'Register the post-dated cheques received from customers and issued to vendors, settle their '
                   'invoices at once, deposit them, clear them into the bank on their date and handle the bounced '
                   'ones.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/pdc_data.xml',
        'views/account_pdc_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.png'],
}
