{
    'name': 'Odoo 20 Assets Management',
    'version': '2.0.4',
    'author': 'Odoo Mates, Odoo SA',
    'depends': ['account'],
    'description': """Manage assets owned by a company or a person. 
        Keeps track of depreciation's, and creates corresponding journal entries""",
    'summary': 'Odoo 20 Assets Management',
    'category': 'Accounting',
    'sequence': 10,
    'license': 'LGPL-3',
    'images': ['static/description/assets.gif'],
    'data': [
        'security/ir.access.csv',
        'wizard/asset_modify_views.xml',
        'wizard/asset_pause_views.xml',
        'wizard/asset_sell_views.xml',
        'wizard/asset_depreciation_schedule_views.xml',
        'views/account_asset_views.xml',
        'views/account_move_views.xml',
        'views/account_asset_templates.xml',
        'views/asset_category_views.xml',
        'views/product_views.xml',
        'views/res_config_settings_views.xml',
        'report/account_asset_report_views.xml',
        'report/report_depreciation_schedule.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_account_asset/static/src/scss/account_asset.scss',
        ],
    },
}
