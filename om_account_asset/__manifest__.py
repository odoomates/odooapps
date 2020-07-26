# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Odoo 12 Assets Management',
    'author': 'Odoo SA, Odoo Mates',
    'depends': ['account'],
    'description': """Manage assets owned by a company or a person. 
    Keeps track of depreciations, and creates corresponding journal entries""",
    'summary': 'Odoo 12 Assets Management',
    'website': 'http://odoomates.tech',	
    'category': 'Accounting',
    'sequence': 32,
    'images': ['static/description/assets.gif'],
    'data': [
        'security/account_asset_security.xml',
        'security/ir.model.access.csv',
        'wizard/asset_depreciation_confirmation_wizard_views.xml',
        'wizard/asset_modify_views.xml',
        'views/account_asset_views.xml',
        'views/account_invoice_views.xml',
        'views/account_asset_templates.xml',
        'views/product_views.xml',
        'views/res_config_settings_views.xml',
        'report/account_asset_report_views.xml',
        'data/account_asset_data.xml',
    ],
    'qweb': [
        "static/src/xml/account_asset_template.xml",
    ],
}
