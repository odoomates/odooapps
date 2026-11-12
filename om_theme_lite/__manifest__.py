{
    'name': 'Odoo Mates Theme Lite',
    'version': '20.0.1.0.3',
    'category': 'Productivity',
    'summary': 'Backend Theme Odoo 20, Odoo 20 UI Theme, Backend UI, App Launcher, Odoo 20 Theme',
    'description': """
The familiar plum and teal look of Odoo for the Odoo 20 Community backend, a home page that
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
    'live_test_url': 'https://www.youtube.com/watch?v=2WOTuBSjX20',
    'depends': ['web', 'mail', 'base_setup'],
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
            'om_theme_lite/static/src/theme/**/*',
            'om_theme_lite/static/src/launcher/**/*',
        ],
        # Community ships the dark bundle but no dark palette; dark_variables.scss
        # supplies one. It is prepended so it lands before the bundle pulls in
        # web.assets_web and, with it, every !default it has to beat.
        # web.dark_mode_variables is where modules such as onboarding put their own
        # dark values; Community defines it but no bundle includes it.
        'web.assets_web_dark': [
            ('prepend', 'om_theme_lite/static/src/scss/dark_variables.scss'),
            ('include', 'web.dark_mode_variables'),
            'om_theme_lite/static/src/scss/theme.dark.scss',
        ],
        # pivot and graph styles are loaded lazily from their own bundle, which
        # compiles on its own and needs the dark palette too
        'web.assets_backend_lazy_dark': [
            ('prepend', 'om_theme_lite/static/src/scss/dark_variables.scss'),
            ('include', 'web.dark_mode_variables'),
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
