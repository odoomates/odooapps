from odoo.tests import BaseCase, tagged

from ..tools import WooAuthError, WooClient, WooError, WooUserError, normalize_site_url
from .common import mock_woo


@tagged('post_install', '-at_install')
class TestClient(BaseCase):

    def client(self, **kwargs):
        return WooClient('https://shop.example.com', 'ck', 'cs', sleep=lambda s: None, **kwargs)

    def test_normalize_site_url(self):
        self.assertEqual(normalize_site_url('Shop.Example.com/'), 'https://shop.example.com')
        self.assertEqual(normalize_site_url('https://example.com/shop/wp-admin/'), 'https://example.com/shop')
        self.assertEqual(normalize_site_url('http://example.com/wp-json'), 'http://example.com')

    def test_pages_and_auth(self):
        with mock_woo({'GET products': lambda params, body: (
                200, [{'id': i} for i in range(100)] if params['page'] == 1 else [{'id': 100}],
                {'X-WP-TotalPages': '2'})}) as fake:
            items = list(self.client().paginate('products', {'status': 'any'}))
        self.assertEqual(len(items), 101)
        self.assertEqual([c[2]['page'] for c in fake.calls], [1, 2])
        self.assertEqual(fake.calls[0][2]['per_page'], 100)
        with mock_woo({'GET orders/1': {'id': 1}}) as fake:
            self.client(query_auth=True).get('orders/1')
        self.assertEqual(fake.calls[0][2]['consumer_key'], 'ck')

    def test_plain_permalinks(self):
        with mock_woo({'GET orders/1': {'id': 1}}) as fake:
            self.assertEqual(self.client(rest_route=True).get('orders/1'), {'id': 1})
        self.assertEqual(fake.calls[0][1], 'orders/1')

    def test_errors(self):
        with mock_woo({'GET a': (401, {'code': 'woocommerce_rest_cannot_view', 'message': 'Sorry'})}):
            with self.assertRaises(WooAuthError):
                self.client().get('a')
        with mock_woo({'GET a': (404, {'code': 'woocommerce_rest_shop_order_invalid_id'})}):
            self.assertIsNone(self.client().get('a'))
        with mock_woo({'GET a': (404, {'code': 'rest_no_route', 'message': 'No route'})}):
            with self.assertRaises(WooUserError):
                self.client().get('a')
        with mock_woo({'GET a': (503, {'message': 'busy'})}):
            with self.assertRaises(WooError):
                self.client().get('a')
        with mock_woo({'GET a': (200, '<html>Not WordPress</html>')}):
            with self.assertRaises(WooUserError):
                self.client().get('a')

    def test_batch(self):
        def answer(params, body):
            return {'update': [{'id': i['id']} for i in body['update']]}
        with mock_woo({'POST products/batch': answer}) as fake:
            done = self.client().batch('products', update=[{'id': i} for i in range(150)])
        self.assertEqual(len(done), 150)
        self.assertEqual([len(b['update']) for b in fake.bodies('POST products/batch')], [100, 50])
        with mock_woo({'POST products/batch': {'update': [{'id': 1, 'error': {'message': 'Invalid ID.'}}]}}):
            with self.assertRaises(WooUserError):
                self.client().batch('products', update=[{'id': 1}])
