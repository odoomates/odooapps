import hashlib
import hmac
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.om_shopify.tools import ShopifyAuthError

from .common import LOCATIONS_ANSWER, SHOP_ANSWER, mock_shopify


def sign(secret, params):
    message = '&'.join(f'{k}={v}' for k, v in sorted(params.items()))
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


@tagged('post_install', '-at_install')
class TestOAuth(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store = cls.env['om.shopify.store'].create({
            'name': 'Partner Shop', 'shop_domain': 'partner-shop.myshopify.com', 'auth_type': 'oauth',
            'client_id': 'app-id', 'client_secret': 'app-secret',
        })

    def _start(self):
        self.authenticate('admin', 'admin')
        response = self.url_open(f'/om_shopify/oauth/start/{self.store.id}', allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        location = urlparse(response.headers['Location'])
        self.assertEqual(location.netloc, 'partner-shop.myshopify.com')
        self.assertEqual(location.path, '/admin/oauth/authorize')
        query = {k: v[0] for k, v in parse_qs(location.query).items()}
        self.assertEqual(query['client_id'], 'app-id')
        self.assertIn('write_orders', query['scope'])
        self.assertTrue(query['redirect_uri'].endswith('/om_shopify/oauth/callback'))
        return query['state']

    def _callback(self, params, **answers):
        with mock_shopify({'OmShopifyShop': SHOP_ANSWER, 'OmShopifyLocations': LOCATIONS_ANSWER, **answers},
                          token={'access_token': 'shpat_oauth', 'scope': 'read_products,write_orders',
                                 'expires_in': 3600, 'refresh_token': 'shprt_1',
                                 'refresh_token_expires_in': 7776000}) as fake:
            response = self.url_open('/om_shopify/oauth/callback?' + '&'.join(f'{k}={v}' for k, v in params.items()),
                                     allow_redirects=False)
        return response, fake

    def test_install_by_link(self):
        state = self._start()
        params = {'code': 'abc', 'shop': 'partner-shop.myshopify.com', 'state': state, 'timestamp': '1763290000'}
        response, fake = self._callback({**params, 'hmac': sign('app-secret', params)})
        self.assertEqual(response.status_code, 303, response.text)
        exchange = next(c for c in fake.calls if c[0] == 'token')
        self.assertEqual(exchange[1]['code'], 'abc')
        self.assertEqual(exchange[1]['expiring'], '1')
        store = self.store
        store.invalidate_recordset()
        self.assertEqual(store.state, 'connected')
        self.assertEqual(store.access_token, 'shpat_oauth')
        self.assertEqual(store.refresh_token, 'shprt_1')
        self.assertEqual(store.oauth_granted_scopes, 'read_products,write_orders')
        self.assertFalse(store.sudo().oauth_state_hash, "a state is used once")
        response, _fake = self._callback({**params, 'hmac': sign('app-secret', params)})
        self.assertEqual(response.status_code, 403, "the same callback cannot be replayed")

    def test_forged_or_wrong_callback(self):
        state = self._start()
        params = {'code': 'abc', 'shop': 'partner-shop.myshopify.com', 'state': state, 'timestamp': '1'}
        with self.assertLogs('odoo.addons.om_shopify.controllers.oauth', 'WARNING') as logs:
            response, fake = self._callback({**params, 'hmac': sign('forged', params)})
            self.assertEqual(response.status_code, 403)
            self.assertFalse([c for c in fake.calls if c[0] == 'token'], "no code exchange without the signature")
            other = {**params, 'shop': 'evil-shop.myshopify.com'}
            response, _fake = self._callback({**other, 'hmac': sign('app-secret', other)})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(len(logs.records), 2, "each refused callback is logged")
        response, _fake = self._callback({**params, 'state': 'unknown', 'hmac': 'x'})
        self.assertEqual(response.status_code, 403)
        self.store.invalidate_recordset()
        self.assertFalse(self.store.access_token)

    def test_refresh_rotates_the_refresh_token(self):
        self.store.write({'access_token': 'shpat_old', 'refresh_token': 'shprt_old', 'state': 'connected',
                          'token_expires_at': fields.Datetime.now() - timedelta(minutes=1)})
        with mock_shopify({'OmShopifyShop': SHOP_ANSWER},
                          token={'access_token': 'shpat_new', 'expires_in': 3600, 'refresh_token': 'shprt_new',
                                 'refresh_token_expires_in': 7776000}) as fake:
            self.store._shopify_execute('query OmShopifyShop { shop { id } }')
        refresh = next(c for c in fake.calls if c[0] == 'token')
        self.assertEqual(refresh[1]['grant_type'], 'refresh_token')
        self.assertEqual(refresh[1]['refresh_token'], 'shprt_old')
        self.assertEqual(fake.calls[-1][2], 'shpat_new', "the call uses the new token")
        self.store.invalidate_recordset()
        self.assertEqual(self.store.refresh_token, 'shprt_new')
        # a refused refresh token: the store asks to connect again
        self.store.write({'token_expires_at': fields.Datetime.now() - timedelta(minutes=1)})
        # (not assertRaises: it would roll back the state saved in a transaction of its own)
        refused = None
        with mock_shopify({}, token=(400, {'error': 'invalid_grant'})):
            try:
                self.store._shopify_execute('query OmShopifyShop { shop { id } }')
            except ShopifyAuthError as e:
                refused = e
        self.assertIn('invalid_grant', str(refused))
        self.store.invalidate_recordset()
        self.assertEqual(self.store.state, 'error')
        self.assertIn('Connect with Shopify', self.store.last_error)

    def test_install_from_shopify(self):
        self.authenticate('admin', 'admin')
        params = {'shop': 'partner-shop.myshopify.com', 'timestamp': '1763290000'}
        response = self.url_open('/om_shopify/oauth/install?shop=partner-shop.myshopify.com&timestamp=1763290000'
                                 f"&hmac={sign('app-secret', params)}", allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/admin/oauth/authorize', response.headers['Location'])
        response = self.url_open('/om_shopify/oauth/install?shop=partner-shop.myshopify.com&hmac=bad',
                                 allow_redirects=False)
        self.assertEqual(response.status_code, 404)
