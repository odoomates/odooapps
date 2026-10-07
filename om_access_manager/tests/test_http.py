import re

from odoo import http
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
        page = self.url_open('/web?debug=1').text
        return re.search(r'debug: "([^"]*)"', page).group(1)

    def test_debug_mode_without_a_profile(self):
        self.assertEqual(self._page_debug(), '1')

    def test_block_developer_mode_on_the_web_client_page(self):
        # /web is an auth='none' route: the hook must find the user in the session
        self.env['om.access.profile'].create({
            'name': 'No Debug', 'block_developer_mode': True, 'user_ids': [(6, 0, self.user.ids)],
        })
        self.assertEqual(self._page_debug(), '')

    def test_block_login_ends_the_open_session(self):
        self.authenticate(self.user.login, self.password)
        self.assertEqual(self.url_open('/web', allow_redirects=False).status_code, 200)
        self.env['om.access.profile'].create({
            'name': 'On Leave', 'block_login': True, 'user_ids': [(6, 0, self.user.ids)],
        })
        response = self.url_open('/web', allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/web/login', response.headers['Location'])
        # and signing in again is refused, from a fresh session
        self.authenticate(None, None)
        response = self.url_open('/web/login', data={
            'login': self.user.login, 'password': self.password, 'csrf_token': http.Request.csrf_token(self),
        })
        self.assertIn('not allow you to sign in', response.text)
        response = self.url_open('/web', allow_redirects=False)
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
            f'/web#action=om_access_manager.om_access_profile_action&id={profile.id}&view_type=form', code,
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
            // a filter reading the user is shown as text on Odoo 16
            const field = document.querySelector('.modal .o_field_widget[name=domain]');
            const shown = (field.querySelector('textarea') || {}).value || field.textContent;
            if (!shown.includes("('user_id', '=', uid)")) {
                throw new Error('the editor does not show the filter: ' + shown);
            }
            console.log('test successful');
        })()"""
        self.browser_js(
            f'/web?debug=1#action=om_access_manager.om_access_profile_action&id={profile.id}&view_type=form', code,
            login='admin', timeout=90)
        self.assertEqual(profile.model_ids.domain, "[('user_id', '=', uid)]")

    def test_configure_from_the_menu_tree(self):
        """ A manager sets everything from the menu tree; the user gets it. """
        group = self.env['res.groups'].create({'name': 'OM Panel Test Group'})
        self.env['ir.model.access'].create({
            'name': 'om_access_manager panel test: tags', 'group_id': group.id, 'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': True,
            'model_id': self.env['ir.model']._get('res.partner.category').id})
        self.user.groups_id |= group
        action = self.env['ir.actions.act_window'].create({
            'name': 'OM Tags', 'res_model': 'res.partner.category', 'view_mode': 'tree,form'})
        app = self.env['ir.ui.menu'].create({'name': 'OM Panel App'})
        tags = self.env['ir.ui.menu'].create({'name': 'OM Tags', 'parent_id': app.id,
                                              'action': f'ir.actions.act_window,{action.id}'})
        profile = self.env['om.access.profile'].create({'name': 'Panel Profile', 'user_ids': [(6, 0, self.user.ids)]})
        report = self.env['ir.actions.report'].create({
            'name': 'OM Tag Sheet', 'model': 'res.partner.category', 'report_name': 'base.om_tag_sheet'})
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
            const checkbox = (scope, label) => [...document.querySelectorAll(scope + ' .form-check')]
                .find((check) => check.textContent.trim() === label).querySelector('input');
            const search = await until('.o_om_menu_tree_search');
            search.value = 'OM Tags';
            search.dispatchEvent(new Event('input', { bubbles: true }));
            (await until('.o_om_menu_tree_row[data-menu-id="%(tags)s"] .o_om_menu_tree_name')).click();
            await until('.o_om_data_rights');
            checkbox('.o_om_data_rights', 'Create').click();
            await wait(1500);
            (await until('.o_om_panel_section[data-section=fields] .o_om_section_toggle')).click();
            (await until('.o_om_panel_row[data-field=color] button[data-mode=hide]')).click();
            await wait(1500);
            // pages, filters and views: one section each
            for (const section of ['pages', 'filters', 'views']) {
                await until(`.o_om_panel_section[data-section=${section}]`);
            }
            await until('.o_om_menu_tree_row[data-menu-id="%(tags)s"] .o_om_mark.fa-lock');
            // the app: read only for everything below
            (await until('.o_om_menu_tree_row[data-menu-id="%(app)s"] .o_om_menu_tree_name')).click();
            await until('.o_om_branch_rights');
            (await until('.o_om_level[data-level=readonly]')).click();
            await wait(1500);
            await until('.o_om_menu_tree_row[data-menu-id="%(app)s"] .o_om_mark.fa-sitemap');
            // a report, from its row under the menu
            search.value = 'OM Tag Sheet';
            search.dispatchEvent(new Event('input', { bubbles: true }));
            (await until('.o_om_tree_print[data-print="ir.actions.report,%(report)s"] input')).click();
            await wait(1500);
            await until('.o_om_tree_print[data-print="ir.actions.report,%(report)s"] .text-decoration-line-through');
            console.log('test successful');
        })()""" % {'tags': tags.id, 'app': app.id, 'report': report.id}
        self.browser_js(
            f'/web#action=om_access_manager.om_access_profile_action&id={profile.id}&view_type=form', code,
            login='admin', timeout=120)
        self.assertEqual((profile.model_ids.model, profile.model_ids.perm_create), ('res.partner.category', False))
        self.assertEqual((profile.field_ids.field_id.name, profile.field_ids.mode), ('color', 'hide'))
        self.assertEqual((profile.menu_rule_ids.menu_id, profile.menu_rule_ids.perm_write), (app, False))
        self.assertEqual(profile.hidden_report_ids, report)
        # the user, in the web client: no Create button on the tags
        user_code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            for (let tries = 0; tries < 75 && !document.querySelector('.o_list_view'); tries++) {
                await wait(200);
            }
            await wait(500);
            if (!document.querySelector('.o_list_view')) {
                throw new Error('no list');
            }
            if (document.querySelector('.o_list_button_add')) {
                throw new Error('the user can still create');
            }
            console.log('test successful');
        })()"""
        # Odoo 16 signs the browser in with the login as the password
        self.user.password = self.user.login
        self.browser_js(f'/web#action={action.id}', user_code, login=self.user.login, timeout=90)
