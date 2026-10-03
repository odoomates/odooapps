import re

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAccessProfileHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-http-pw'
        cls.user = new_test_user(cls.env, 'om_access_http_user', groups='base.group_user',
                                 password=cls.password)

    def _page_debug(self):
        self.authenticate(self.user.login, self.password)
        page = self.url_open('/odoo?debug=1').text
        return re.search(r'debug: "([^"]*)"', page).group(1)

    def test_debug_mode_without_a_profile(self):
        self.assertEqual(self._page_debug(), '1')

    def test_block_developer_mode_on_the_web_client_page(self):
        # /odoo is an auth='none' route: the hook must find the user in the session
        self.env['om.access.profile'].create({
            'name': 'No Debug', 'block_developer_mode': True, 'user_ids': [(6, 0, self.user.ids)],
        })
        self.assertEqual(self._page_debug(), '')

    def test_block_login_ends_the_open_session(self):
        self.authenticate(self.user.login, self.password)
        self.assertEqual(self.url_open('/odoo', allow_redirects=False).status_code, 200)
        self.env['om.access.profile'].create({
            'name': 'On Leave', 'block_login': True, 'user_ids': [(6, 0, self.user.ids)],
        })
        response = self.url_open('/odoo', allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/web/login', response.headers['Location'])
        # and signing in again is refused, from a fresh session
        self.authenticate(None, None)
        response = self.url_open('/web/login', data={
            'login': self.user.login, 'password': self.password, 'csrf_token': self.csrf_token(),
        })
        self.assertIn('not allow you to sign in', response.text)
        response = self.url_open('/odoo', allow_redirects=False)
        self.assertEqual(response.status_code, 303)

    def test_menu_tree_hides_a_branch(self):
        profile = self.env['om.access.profile'].create({'name': 'Tree Profile'})
        discuss = self.env.ref('mail.menu_root_discuss')
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector) => {
                for (let tries = 0; tries < 75; tries++) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element;
                    }
                    await wait(200);
                }
                throw new Error('not found: ' + selector);
            };
            await until('.o_notebook .nav-link');
            [...document.querySelectorAll('.o_notebook .nav-link')]
                .find((link) => link.textContent.includes('Menus')).click();
            const row = await until('.o_om_menu_tree_row[data-menu-id="%(menu)s"]');
            row.querySelector('input[type=checkbox]').click();
            await wait(500);
            if (!row.querySelector('.text-decoration-line-through')) {
                throw new Error('the app is not shown as hidden');
            }
            const search = document.querySelector('.o_om_menu_tree_search');
            search.value = 'Discuss';
            search.dispatchEvent(new Event('input', { bubbles: true }));
            await wait(300);
            if (!document.querySelector('.o_om_menu_tree_row[data-menu-id="%(menu)s"]')) {
                throw new Error('the search lost the app');
            }
            (await until('.o_form_button_save')).click();
            await wait(1500);
            console.log('test successful');
        })()""" % {'menu': discuss.id}
        self.browser_js(
            f'/odoo/action-om_access_manager.om_access_profile_action/{profile.id}', code,
            login='admin', timeout=90)
        self.assertEqual(profile.hidden_menu_ids, discuss)

    def test_rule_form_presets(self):
        profile = self.env['om.access.profile'].create({'name': 'Rule Profile', 'model_ids': [(0, 0, {
            'model_id': self.env['ir.model']._get('res.partner').id,
        })]})
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector) => {
                for (let tries = 0; tries < 75; tries++) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element;
                    }
                    await wait(200);
                }
                throw new Error('not found: ' + selector);
            };
            await until('.o_notebook .nav-link');
            [...document.querySelectorAll('.o_notebook .nav-link')]
                .find((link) => link.textContent.trim() === 'Models').click();
            (await until('.o_field_widget[name=model_ids] button[name=action_open_rule]')).click();
            await until('.modal .o_field_widget[name=domain]');
            (await until('.modal button[name=action_preset_own]')).click();
            await wait(1500);
            if (!document.querySelector('.modal .o_field_widget[name=domain]').textContent.includes('Salesperson')) {
                throw new Error('the editor does not show the filter: '
                    + document.querySelector('.modal .o_field_widget[name=domain]').textContent);
            }
            console.log('test successful');
        })()"""
        self.browser_js(
            f'/odoo/action-om_access_manager.om_access_profile_action/{profile.id}', code,
            login='admin', timeout=90)
        self.assertEqual(profile.model_ids.domain, "[('user_id', '=', uid)]")
