# The Print and Action menus of a model, the chatter parts, and the home page.
from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException


@tagged('post_install', '-at_install')
class TestMenusAndChatter(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-menus-pw'
        cls.user = new_test_user(cls.env, 'om_access_menus_user',
                                 groups='base.group_user,base.group_partner_manager', password=cls.password)
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partner = cls.env['res.partner'].create({'name': 'Chatty'})
        cls.report = cls.env['ir.actions.report'].create({
            'name': 'Partner Sheet', 'model': 'res.partner', 'report_type': 'qweb-html',
            'report_name': 'base.contact_name', 'binding_model_id': cls.partner_model.id,
        })
        cls.server_action = cls.env['ir.actions.server'].create({
            'name': 'Partner Tool', 'model_id': cls.partner_model.id, 'state': 'code', 'code': '',
            'binding_model_id': cls.partner_model.id,
        })

    def _profile(self, **values):
        return self.env['om.access.profile'].create(dict(values, name='Menus', user_ids=[(6, 0, self.user.ids)]))

    def _rule(self, **flags):
        return {'model_ids': [(0, 0, dict(flags, model_id=self.partner_model.id))]}

    def _bindings(self):
        return self.env['ir.actions.actions'].with_user(self.user).get_bindings('res.partner')

    def test_hide_the_print_menu_of_a_model(self):
        self.assertIn(self.report.id, [entry['id'] for entry in self._bindings().get('report', [])])
        self._profile(**self._rule(hide_print=True))
        self.assertFalse(self._bindings().get('report'))
        Profile = self.env['om.access.profile'].with_user(self.user)
        with self.assertRaises(AccessError):
            Profile._check_action(self.report.id)
        with self.assertRaises(AccessError):
            self.env['ir.actions.report'].with_user(self.user)._render_qweb_html(
                self.report.report_name, self.partner.ids)
        # the Action menu stays
        self.assertIn(self.server_action.id, [entry['id'] for entry in self._bindings().get('action', [])])

    def test_hide_the_action_menu_of_a_model(self):
        self._profile(**self._rule(hide_action_menu=True))
        self.assertFalse(self._bindings().get('action'))
        with self.assertRaises(AccessError):
            self.env['om.access.profile'].with_user(self.user)._check_action(self.server_action.id)
        # the Print menu stays
        self.assertTrue(self._bindings().get('report'))

    def test_the_switches_apply_to_every_model(self):
        self._profile(hide_print_all=True, hide_action_menu_all=True)
        self.assertFalse(self._bindings())

    def test_chatter_parts(self):
        self._profile(**self._rule(hide_send_message=True, hide_attachments=True))
        arch = etree.fromstring(self.env['res.partner'].with_user(self.user).get_view(view_type='form')['arch'])
        classes = (arch.get('class') or '').split()
        self.assertIn('o_om_hide_send_message', classes)
        self.assertIn('o_om_hide_attachments', classes)
        self.assertNotIn('o_om_hide_followers', classes)

    def _post(self, subtype):
        return self.make_jsonrpc_request('/mail/message/post', {
            'thread_model': 'res.partner', 'thread_id': self.partner.id,
            'post_data': {'body': 'Hello', 'message_type': 'comment', 'subtype_xmlid': subtype},
        })

    def test_send_message_is_refused_and_log_note_is_not(self):
        self._profile(hide_send_message_all=True)
        self.authenticate(self.user.login, self.password)
        with self.assertRaises(JsonRpcException):
            self._post('mail.mt_comment')
        self.assertTrue(self._post('mail.mt_note')['message_id'])

    def test_home_page(self):
        action = self.env['ir.actions.act_window'].create({'name': 'Landing', 'res_model': 'res.partner'})
        self._profile(home_action_id=action.id)
        self.authenticate(self.user.login, self.password)
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info['home_action_id'], action.id)

    def test_chatter_and_home_page_in_the_browser(self):
        action = self.env['ir.actions.act_window'].create({
            'name': 'Landing Contacts', 'res_model': 'res.partner', 'view_mode': 'list,form'})
        self._profile(home_action_id=action.id, hide_send_message_all=True, hide_followers_all=True)
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
            // signing in lands on the home page of the profile
            await until('.o_list_view');
            const title = document.querySelector('.o_breadcrumb, .o_control_panel').innerText;
            if (!title.includes('Landing Contacts')) {
                throw new Error('not on the home page: ' + title);
            }
            window.location.hash = '';
            (await until('.o_data_row td.o_data_cell')).click();
            const logNote = await until('.o-mail-Chatter-logNote');
            const visible = (element) => element && element.offsetParent !== null;
            if (!visible(logNote)) {
                throw new Error('Log note is hidden');
            }
            if (visible(document.querySelector('.o-mail-Chatter-sendMessage'))) {
                throw new Error('Send message is shown');
            }
            if (visible(document.querySelector('.o-mail-Followers'))) {
                throw new Error('the followers are shown');
            }
            console.log('test successful');
        })()"""
        self.browser_js('/odoo', code, login=self.user.login, timeout=90)
