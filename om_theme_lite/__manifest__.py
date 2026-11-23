{
    'name': 'Odoo Mates Theme Lite',
    'version': '15.0.1.0.1',
    'category': 'Productivity',
    'summary': 'Backend Theme Odoo 15, Odoo 15 UI Theme, Backend UI, App Launcher, Odoo 15 Theme',
    'description': """
The familiar plum and teal look of Odoo for the Odoo 15 Community backend, a home page that
lists every app, and a real dark mode.

The theme works through the variables Odoo already exposes, so buttons, links, the navbar
and every view are recoloured together rather than patched one by one. Each user chooses
Light, Dark or System, an apps sidebar, the chatter position and the dialog size in My
Preferences; the company sets a home screen background and a favicon in Settings. It also
brings a matching login page, a clearer chatter, full screen dialogs, a refresh button and
list column widths that are remembered.
""",
    'sequence': 10,
    'author': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'depends': ['web', 'mail', 'base_setup', 'om_chatter_position'],
    'data': [
        'data/ir_actions_client.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'views/webclient_templates.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        # prepended, not appended: every Odoo variable is !default AND the derived ones
        # (link colour, navbar background, the button maps) are computed further down
        # the same file. Appending would set the base colours but leave everything
        # derived from them on Odoo's defaults.
        'web._assets_primary_variables': [
            ('prepend', 'om_theme_lite/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'om_theme_lite/static/src/scss/theme.scss',
            'om_theme_lite/static/src/theme/*.js',
            'om_theme_lite/static/src/launcher/*.js',
            'om_theme_lite/static/src/launcher/*.scss',
        ],
        'web.assets_qweb': [
            'om_theme_lite/static/src/theme/*.xml',
            'om_theme_lite/static/src/launcher/*.xml',
        ],
        # Community has no dark mode, so the dark bundles are the module's own: the
        # light ones with a dark palette prepended, so it lands before the bundle
        # pulls in the light one and, with it, every !default it has to beat.
        'om_theme_lite.dark_assets_common': [
            'om_theme_lite/static/src/scss/dark_variables.scss',
            ('include', 'web.assets_common'),
        ],
        'om_theme_lite.dark_assets_backend': [
            'om_theme_lite/static/src/scss/dark_variables.scss',
            ('include', 'web.assets_backend'),
            'om_theme_lite/static/src/scss/theme.dark.scss',
        ],
        # the login page
        'web.assets_frontend': [
            'om_theme_lite/static/src/scss/login.scss',
        ],
        'web.assets_tests': [
            'om_theme_lite/static/tests/tours/*.js',
        ],
    },
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
}
