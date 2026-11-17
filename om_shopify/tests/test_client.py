from odoo.tests import BaseCase, tagged

from odoo.addons.om_shopify.tools import (
    ShopifyAuthError,
    ShopifyClient,
    ShopifyThrottledError,
    ShopifyUserError,
    normalize_shop_domain,
    topic_to_enum,
)

from .common import mock_shopify

THROTTLED = {'errors': [{'message': 'Throttled', 'extensions': {'code': 'THROTTLED'}}],
             'extensions': {'cost': {'requestedQueryCost': 202, 'actualQueryCost': None,
                                     'throttleStatus': {'maximumAvailable': 2000, 'currentlyAvailable': 2,
                                                        'restoreRate': 100}}}}


@tagged('post_install', '-at_install')
class TestClient(BaseCase):

    def _client(self, **kwargs):
        self.waits = []
        return ShopifyClient('demo-shop.myshopify.com', 'shpat_x', sleep=self.waits.append, **kwargs)

    def test_helpers(self):
        self.assertEqual(normalize_shop_domain('https://Demo-Shop.myshopify.com/admin/products'),
                         'demo-shop.myshopify.com')
        self.assertEqual(normalize_shop_domain('demo-shop'), 'demo-shop.myshopify.com')
        self.assertEqual(topic_to_enum('orders/create'), 'ORDERS_CREATE')
        self.assertEqual(topic_to_enum('app/uninstalled'), 'APP_UNINSTALLED')

    def test_throttled_then_ok(self):
        client = self._client()
        with mock_shopify({'Q': [THROTTLED, {'data': {'shop': {'id': 1}}}]}) as fake:
            data = client.execute('query Q { shop { id } }')
        self.assertEqual(data, {'shop': {'id': 1}})
        self.assertEqual(self.waits, [2.0], "waits until the 200 missing points are back, at 100 a second")
        self.assertEqual(fake.calls[0][2], 'shpat_x')

    def test_throttled_too_long_is_retried_later(self):
        client = self._client(max_throttle_wait=3)
        with mock_shopify({'Q': THROTTLED}), self.assertRaises(ShopifyThrottledError) as e:
            client.execute('query Q { shop { id } }')
        self.assertGreaterEqual(e.exception.delay, 30)

    def test_errors(self):
        client = self._client()
        with mock_shopify({'Q': (401, {'errors': 'Invalid API key'})}), self.assertRaises(ShopifyAuthError):
            client.execute('query Q { shop { id } }')
        with mock_shopify({'Q': {'errors': [{'message': "Field 'x' doesn't exist"}]}}), \
                self.assertRaises(ShopifyUserError):
            client.execute('query Q { x }')
        with mock_shopify({'M': {'data': {'productSet': {'userErrors': [{'field': ['input', 'title'],
                                                                          'message': "can't be blank"}]}}}}), \
                self.assertRaisesRegex(ShopifyUserError, "input.title: can't be blank"):
            client.mutate('mutation M { productSet { userErrors { field message } } }', {}, 'productSet')

    def test_paginate(self):
        pages = [
            {'data': {'products': {'nodes': [{'id': 1}, {'id': 2}],
                                   'pageInfo': {'hasNextPage': True, 'endCursor': 'c1'}}}},
            {'data': {'products': {'nodes': [{'id': 3}], 'pageInfo': {'hasNextPage': False, 'endCursor': 'c2'}}}},
        ]
        client = self._client()
        with mock_shopify({'P': pages}) as fake:
            nodes = list(client.paginate('query P($cursor: String) { products }', {'first': 2}, 'products'))
        self.assertEqual([n['id'] for n in nodes], [1, 2, 3])
        self.assertEqual([c[1]['cursor'] for c in fake.calls], [None, 'c1'])

    def test_client_credentials_token(self):
        with mock_shopify(token={'access_token': 'tok', 'expires_in': 86399}) as fake:
            token, seconds = ShopifyClient.fetch_client_credentials_token('demo-shop.myshopify.com', 'id', 'secret')
        self.assertEqual((token, seconds), ('tok', 86399))
        self.assertEqual(fake.calls[0][1]['grant_type'], 'client_credentials')
        with mock_shopify(token=(400, {'error': 'invalid_client'})), self.assertRaises(ShopifyAuthError):
            ShopifyClient.fetch_client_credentials_token('demo-shop.myshopify.com', 'id', 'bad')
