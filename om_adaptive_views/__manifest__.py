{
    'name': 'Odoo Mates Adaptive Views',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Screens and menus that adapt to how your company works: per role, per person, on their own',
    'description': """
Adaptive Views watches how your team actually uses each screen - which fields get filled
in, which filters are applied, which columns are switched on - and suggests changes:
fold the fields nobody edits, make the filter everyone applies the default, show the
column everyone turns on, put the menus in the order they are opened. Each change is
applied with one click and undone with another.

Roles are learnt apart, each person gets their own default filter and menu order, the
clearest changes can apply on their own with a weekly digest, every change is kept in a
journal, a change can be previewed first, and the changes move between databases in one file.

Only counts are collected, never the values typed. Nothing in your views is rewritten:
the changes are applied while Odoo builds the screen, per company.
""",
    'sequence': 10,
    'author': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'depends': ['web', 'base_setup', 'bus', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/om_adapt_rule_views.xml',
        'views/om_usage_stat_views.xml',
        'views/om_adapt_report_views.xml',
        'views/om_adapt_journal_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/om_adapt_transfer_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_adaptive_views/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
}
