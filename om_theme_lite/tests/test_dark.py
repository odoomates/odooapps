from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestColorScheme(TransactionCase):

    def test_default_is_light(self):
        self.assertEqual(self.env['ir.http'].color_scheme(), 'light')

    def test_the_user_preference_picks_the_dark_bundle(self):
        self.env.user.om_color_scheme = 'dark'
        self.assertEqual(self.env['ir.http'].color_scheme(), 'dark')

    def test_the_scheme_is_per_user(self):
        other = self.env['res.users'].create({
            'name': 'Night owl', 'login': 'om_night_owl', 'om_color_scheme': 'dark',
        })
        self.env.user.om_color_scheme = 'light'
        self.assertEqual(self.env['ir.http'].color_scheme(), 'light')
        self.assertEqual(
            self.env['ir.http'].with_user(other).color_scheme(), 'dark',
            "one user's choice must not follow another user around")

    def test_a_user_may_set_their_own_scheme(self):
        """The preference is the user's own, so it is writeable without write
        access on res.users."""
        other = self.env['res.users'].create({
            'name': 'Plain user', 'login': 'om_plain_user',
            'group_ids': [(4, self.env.ref('base.group_user').id)],
        })
        other.with_user(other).om_color_scheme = 'dark'
        self.assertEqual(other.om_color_scheme, 'dark')


@tagged('post_install', '-at_install')
class TestDarkBrowser(HttpCase):

    def test_light_by_default(self):
        self.env.ref('base.user_admin').om_color_scheme = 'light'
        self.start_tour('/odoo', 'om_theme_light_tour', login='admin', timeout=60)

    def test_dark_is_actually_dark(self):
        self.env.ref('base.user_admin').om_color_scheme = 'dark'
        self.start_tour('/odoo/action-base.action_res_users', 'om_theme_dark_tour',
                        login='admin', timeout=60)

    def test_the_systray_toggle_switches_scheme(self):
        """The switch saves the preference; the reload it then triggers is what
        swaps the bundle, and that swap is covered by test_dark_is_actually_dark."""
        admin = self.env.ref('base.user_admin')
        admin.om_color_scheme = 'light'
        self.start_tour('/odoo', 'om_theme_toggle_tour', login='admin', timeout=90)
        admin.invalidate_recordset(['om_color_scheme'])
        self.assertEqual(admin.om_color_scheme, 'dark')
