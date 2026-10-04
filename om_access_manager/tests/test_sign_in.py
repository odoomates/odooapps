# Working hours, allowed networks, one session per user, through real sign-ins
# so both the sign-in check and the end of an open session are covered.
import re
from datetime import datetime, timezone
from unittest.mock import patch

import requests

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, new_test_user, tagged

from .audit import lines_after_transaction

# a Monday
OFFICE_HOURS = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
EVENING = datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc)


@tagged('post_install', '-at_install')
class TestSignIn(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-signin-pw'
        cls.user = new_test_user(cls.env, 'om_access_signin_user', groups='base.group_user',
                                 password=cls.password)

    def _profile(self, **values):
        return self.env['om.access.profile'].create(dict(values, name='Sign-in', user_ids=[(6, 0, self.user.ids)]))

    def _at(self, moment):
        patches = [patch(f'odoo.addons.om_access_manager.models.{module}.utc_now', return_value=moment)
                   for module in ('res_users', 'ir_http')]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _sign_in(self):
        """ Sign in through the form from a new, independent browser session;
        return that session, signed in or not. """
        browser = requests.Session()
        url = self.base_url()
        # the test server answers other clients than the test opener only when told
        with self.allow_requests(all_requests=True):
            page = browser.get(f'{url}/web/login?db={self.env.cr.dbname}', timeout=30)
            field = re.search(r'<input[^>]*csrf_token[^>]*>', page.text).group(0)
            browser.post(f'{url}/web/login', data={
                'login': self.user.login, 'password': self.password,
                'csrf_token': re.search(r'value="([^"]+)"', field).group(1),
            }, timeout=30)
        return browser

    def _audit(self, event):
        self.env.invalidate_all()
        return self.env['om.user.audit.log'].sudo().search([('user_id', '=', self.user.id), ('event', '=', event)])

    def _signed_in(self, browser):
        with self.allow_requests(all_requests=True):
            response = browser.post(f'{self.base_url()}/web/session/check', json={
                'jsonrpc': '2.0', 'method': 'call', 'params': {}}, timeout=30)
        return 'error' not in response.json()

    def test_working_hours(self):
        self._profile(login_tz='UTC', login_slot_ids=[(0, 0, {'dayofweek': '0', 'hour_from': 8, 'hour_to': 17})])
        self._at(EVENING)
        self.assertFalse(self._signed_in(self._sign_in()))
        # the audit log keeps the refused sign-in and its reason
        self.assertIn('working hours', self._audit('login_failed').detail)
        # signed in during the day, the session ends with the working hours
        patch.stopall()
        self._at(OFFICE_HOURS)
        browser = self._sign_in()
        self.assertTrue(self._signed_in(browser))
        patch.stopall()
        self._at(EVENING)
        self.assertFalse(self._signed_in(browser))

    def test_the_hours_follow_the_timezone_of_the_profile(self):
        # 10:00 UTC is 14:00 in Dubai: outside a morning shift there
        self._profile(login_tz='Asia/Dubai', login_slot_ids=[(0, 0, {'dayofweek': '0', 'hour_from': 8, 'hour_to': 12})])
        self._at(OFFICE_HOURS)
        self.assertFalse(self._signed_in(self._sign_in()))

    def test_allowed_networks(self):
        profile = self._profile(allowed_ips='10.0.0.0/8')
        self.assertFalse(self._signed_in(self._sign_in()))
        profile.allowed_ips = '10.0.0.0/8\n127.0.0.1  # this office'
        browser = self._sign_in()
        self.assertTrue(self._signed_in(browser))
        # the session ends when its network is no longer allowed
        profile.allowed_ips = '10.0.0.0/8'
        self.assertFalse(self._signed_in(browser))

    def test_a_wrong_network_is_refused(self):
        with self.assertRaises(ValidationError):
            self._profile(allowed_ips='300.1.2.3')

    def test_one_session_per_user(self):
        self._profile(single_session=True)
        first = self._sign_in()
        self.assertTrue(self._signed_in(first))
        second = self._sign_in()
        self.assertTrue(self._signed_in(second))
        with lines_after_transaction(self.env) as lines:
            self.assertFalse(self._signed_in(first))
        self.assertTrue(self._signed_in(second))
        # the audit log is told why the session ended
        self.assertEqual([(line['event'], line['user_id'], line['detail']) for line in lines],
                         [('session_end', self.user.id, 'Signed in elsewhere (One Session per User)')])

    def test_without_the_switch_sessions_coexist(self):
        self._profile()
        first = self._sign_in()
        second = self._sign_in()
        self.assertTrue(self._signed_in(first) and self._signed_in(second))

    def test_additive_profiles_widen_and_override_ones_narrow(self):
        Profile = self.env['om.access.profile']
        self._profile(login_slot_ids=[(0, 0, {'dayofweek': '0', 'hour_from': 8, 'hour_to': 12})], login_tz='UTC')
        Profile.create({'name': 'Afternoon', 'login_tz': 'UTC', 'user_ids': [(6, 0, self.user.ids)],
                        'login_slot_ids': [(0, 0, {'dayofweek': '0', 'hour_from': 12, 'hour_to': 18})]})
        rules = Profile._resolve(self.user.id)
        self.assertIsNone(rules.login_refusal(datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc), '127.0.0.1'))
        self.assertEqual(rules.login_refusal(EVENING, '127.0.0.1'), 'hours')
        Profile.create({'name': 'Office only', 'strictness': 'override', 'allowed_ips': '10.0.0.0/8',
                        'user_ids': [(6, 0, self.user.ids)]})
        rules = Profile._resolve(self.user.id)
        self.assertEqual(rules.login_refusal(OFFICE_HOURS, '127.0.0.1'), 'network')
