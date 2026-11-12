from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestLauncher(HttpCase):

    def _launcher_url(self):
        action = self.env.ref('om_theme_lite.action_app_launcher')
        return '/odoo/action-%s' % action.id

    def test_launcher_lists_and_searches(self):
        """Tiles render, search filters apps and reaches menu items inside them."""
        self.start_tour(self._launcher_url(), 'om_theme_launcher_tour',
                        login='admin', timeout=90)

    def test_launcher_tile_opens_app(self):
        self.start_tour(self._launcher_url(), 'om_theme_launcher_open_app_tour',
                        login='admin', timeout=90)


@tagged('post_install', '-at_install')
class TestPalette(HttpCase):

    def test_the_palette_reaches_odoo_buttons(self):
        self.start_tour('/odoo/action-base.action_res_users', 'om_theme_palette_tour',
                        login='admin', timeout=60)
