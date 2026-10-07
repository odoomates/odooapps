# Each event is logged once, through the entry point that produces it.
import json
import time
from datetime import timedelta
from unittest.mock import patch

from odoo import fields, http
from odoo.exceptions import AccessDenied
from odoo.http import root
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.om_user_audit.models.ir_http import SEEN_KEY


class AuditMixin:

    def _logs(self, **domain):
        self.env.cr.precommit.run()
        self.env['base'].invalidate_cache()
        return self.env['om.user.audit.log'].sudo().search([(key, '=', value) for key, value in domain.items()])

    def make_jsonrpc_request(self, route, params=None):
        """ Odoo 17's helper of HttpCase. """
        response = self.url_open(route, json.dumps({'id': 0, 'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        response.raise_for_status()
        decoded = response.json()
        if 'error' in decoded:
            raise Exception(decoded['error'])
        return decoded.get('result')


@tagged('post_install', '-at_install')
class TestAuditRules(AuditMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_audit_user', groups='base.group_user,base.group_partner_manager')

    def test_changes_are_logged_with_their_values(self):
        Partner = self.env['res.partner'].with_user(self.user)
        partner = Partner.create({'name': 'Audited', 'phone': '111'})
        partner.write({'phone': '222', 'name': 'Audited'})
        partner.unlink()
        logs = self._logs(model='res.partner', res_id=partner.id)
        self.assertEqual(sorted(logs.mapped('event')), ['create', 'unlink', 'write'])
        edit = logs.filtered(lambda line: line.event == 'write')
        # only what changed
        self.assertEqual(edit.changes, 'Phone: 111 → 222')
        self.assertEqual(edit.user_id, self.user)

    def test_an_editable_computed_field_is_logged(self):
        partner = self.env['res.partner'].with_user(self.user).create({'name': 'Customer'})
        partner.user_id = self.user
        edit = self._logs(model='res.partner', res_id=partner.id, event='write')
        self.assertEqual(edit.changes, f'Salesperson:  → {self.user.name}')

    def test_the_superuser_and_technical_data_are_not_logged(self):
        self.env['res.partner'].sudo().create({'name': 'By the system'})
        self.env['ir.config_parameter'].with_user(self.env.ref('base.user_admin')).set_str('om.test', '1')
        self.assertFalse(self._logs(res_name='By the system'))
        self.assertFalse(self._logs(model='ir.config_parameter'))

    def test_python_reads_are_not_logged(self):
        self.env['res.partner'].with_user(self.user).search([]).read(['name'])
        self.assertFalse(self._logs(event='read'))

    def test_a_rule_narrows_what_is_logged(self):
        category_model = self.env['ir.model']._get('res.partner.category')
        self.env['om.user.audit.rule'].create({'name': 'Tags', 'model_ids': [(6, 0, category_model.ids)],
                                               'log_write': False})
        self.env['res.partner'].with_user(self.user).create({'name': 'Not logged'})
        tag = self.env['res.partner.category'].with_user(self.env.ref('base.user_admin')).create({'name': 'Logged'})
        tag.name = 'Renamed'
        self.assertFalse(self._logs(model='res.partner'))
        self.assertEqual(self._logs(model='res.partner.category').mapped('event'), ['create'])

    def test_a_rule_for_some_users(self):
        other = new_test_user(self.env, 'om_audit_other', groups='base.group_user,base.group_partner_manager')
        self.env['om.user.audit.rule'].create({'name': 'One user', 'user_ids': [(6, 0, other.ids)]})
        self.env['res.partner'].with_user(self.user).create({'name': 'By the user'})
        self.env['res.partner'].with_user(other).create({'name': 'By the other'})
        self.assertEqual(self._logs(model='res.partner').mapped('res_name'), ['By the other'])

    def test_old_lines_are_deleted(self):
        Log = self.env['om.user.audit.log'].sudo()
        old = Log.create({'event': 'other', 'date': fields.Datetime.now() - timedelta(days=100)})
        old_login = Log.create({'event': 'login', 'date': fields.Datetime.now() - timedelta(days=100)})
        recent = Log.create({'event': 'other'})
        self.env['ir.config_parameter'].sudo().set_int('om_user_audit.keep_sign_in_days', 365)
        Log._cron_clean()
        self.assertFalse(old.exists())
        self.assertTrue(old_login.exists())
        self.assertTrue(recent.exists())


@tagged('post_install', '-at_install')
class TestAuditHttp(AuditMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-user-audit-pw-1'
        cls.user = new_test_user(cls.env, 'om_audit_http', password=cls.password,
                                 groups='base.group_user,base.group_partner_manager,base.group_allow_export')
        cls.partner = cls.env['res.partner'].create({'name': 'Read Me'})

    def _call(self, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}})

    def test_sign_in_read_export_print_and_sign_out(self):
        self.authenticate(self.user.login, self.password)
        self.assertEqual(len(self._logs(user_id=self.user.id, event='login')), 1)
        self._call('res.partner', 'web_search_read', [], {
            'domain': [('id', '=', self.partner.id)], 'fields': ['name']})
        read = self._logs(user_id=self.user.id, event='read')
        self.assertEqual((len(read), read.method, read.record_ids), (1, 'web_search_read', str(self.partner.id)))
        data = json.dumps({'model': 'res.partner', 'ids': self.partner.ids, 'domain': [], 'import_compat': False,
                           'fields': [{'name': 'name', 'label': 'Name'}]})
        self.url_open('/web/export/csv', data={'data': data, 'csrf_token': http.WebRequest.csrf_token(self)})
        export = self._logs(user_id=self.user.id, event='export')
        self.assertEqual((len(export), export.record_count), (1, 1))
        # the export reads nothing more in the log
        self.assertEqual(len(self._logs(user_id=self.user.id, event='read')), 1)
        self.env['ir.ui.view'].create({
            'name': 'om_user_audit.test_partner', 'type': 'qweb', 'key': 'om_user_audit.test_partner',
            'arch': '<t t-name="om_user_audit.test_partner"><p t-foreach="docs" t-as="o" t-out="o.name"/></t>'})
        self.env['ir.actions.report'].create({
            'name': 'Partner Sheet', 'model': 'res.partner', 'report_type': 'qweb-html',
            'report_name': 'om_user_audit.test_partner'})
        self.assertIn('Read Me', self.url_open(f'/report/html/om_user_audit.test_partner/{self.partner.id}').text)
        printed = self._logs(user_id=self.user.id, event='print')
        self.assertEqual((len(printed), printed.res_id, printed.detail), (1, self.partner.id, 'Partner Sheet'))
        self.url_open('/web/session/logout', data={'csrf_token': http.WebRequest.csrf_token(self)})
        self.assertEqual(len(self._logs(user_id=self.user.id, event='logout')), 1)

    def test_a_failed_sign_in_survives_the_rollback(self):
        # Odoo 15 signs in on a cursor of its own, and the failure is logged on
        # another: go through the sign-in form, as a person does
        self.authenticate(None, None)
        self.url_open('/web/login', data={
            'login': self.user.login, 'password': 'wrong', 'csrf_token': http.WebRequest.csrf_token(self)})
        failed = self._logs(event='login_failed', login=self.user.login)
        self.assertEqual((len(failed), failed.user_id), (1, self.user))

    def test_xmlrpc_reads_are_logged_with_the_address(self):
        self.xmlrpc_object.execute_kw(self.env.cr.dbname, self.user.id, self.password,
                                      'res.partner', 'read', [self.partner.ids, ['name']])
        read = self._logs(user_id=self.user.id, event='read', method='read')
        self.assertEqual(len(read), 1)
        self.assertEqual(read.ip, '127.0.0.1')

    def test_an_idle_session_is_ended(self):
        self.env['ir.config_parameter'].sudo().set_int('om_user_audit.idle_minutes', 5)
        session = self.authenticate(self.user.login, self.password)
        session[SEEN_KEY] = time.time() - 600
        root.session_store.save(session)
        response = self.url_open('/web', allow_redirects=False)
        self.assertIn('/web/login', response.headers.get('Location', ''))
        self.assertEqual(len(self._logs(user_id=self.user.id, event='session_end')), 1)

    def _sign_in(self):
        """ Sign in through the login form, as a person does. """
        self.authenticate(None, None)
        response = self.url_open('/web/login', data={
            'login': self.user.login, 'password': self.password, 'csrf_token': http.WebRequest.csrf_token(self)},
            allow_redirects=False)
        self.assertEqual(response.status_code, 303)

    def test_ending_a_session(self):
        self.authenticate(self.user.login, self.password)
        self.url_open('/web')
        self.env['base'].invalidate_cache()
        sessions = self.env['om.user.audit.session'].sudo().search([('user_id', '=', self.user.id)])
        self.assertTrue(sessions)
        sessions.with_user(self.env.ref('base.user_admin')).action_om_end()
        response = self.url_open('/web', allow_redirects=False)
        self.assertIn('/web/login', response.headers.get('Location', ''))
        self.assertEqual(len(self._logs(user_id=self.user.id, event='session_end')), 1)

    def test_the_sign_in_email(self):
        self.user.email = 'audit@example.com'
        params = self.env['ir.config_parameter'].sudo()
        params.set_str('om_user_audit.sign_in_mail', 'user')
        self._sign_in()
        mails = self.env['mail.mail'].sudo().search([('subject', 'ilike', self.user.name)])
        self.assertEqual(mails.recipient_ids, self.user.partner_id)
        # only from a new device: the second sign-in from the same browser sends nothing
        params.set_bool('om_user_audit.sign_in_mail_new_only', True)
        with patch.object(type(self.env['res.users']), '_om_sign_in_mail', autospec=True,
                          side_effect=type(self.env['res.users'])._om_sign_in_mail) as sent:
            self._sign_in()
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(len(self.env['mail.mail'].sudo().search([('subject', 'ilike', self.user.name)])), 1)
