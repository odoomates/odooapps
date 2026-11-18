from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import INDEX, SITE, WooCase, mock_woo


@tagged('post_install', '-at_install')
class TestStore(WooCase):

    def connect_routes(self, **extra):
        return {
            'GET /': INDEX,
            'GET settings/general/woocommerce_currency': {'id': 'woocommerce_currency', 'value': 'EUR'},
            'GET settings/products/woocommerce_weight_unit': {'id': 'woocommerce_weight_unit', 'value': 'g'},
            'GET webhooks': [],
            'POST webhooks': lambda params, body: {'id': len(body['topic']), 'status': 'active', **body},
            **extra,
        }

    def test_store_defaults(self):
        self.assertEqual(self.store.site_url, SITE)
        self.assertTrue(self.store.sudo().webhook_secret, "a secret of its own for the webhooks")
        self.assertTrue(self.store.workflow_id)
        self.assertEqual(sorted(self.store.order_status_ids.mapped('code')), ['completed', 'on-hold', 'processing'])
        self.assertTrue(self.store.sudo().consumer_key_encrypted)
        self.assertNotEqual(self.store.sudo().consumer_key_encrypted, 'ck_test')
        with self.assertRaises(ValidationError):
            self.store.site_url = 'http://insecure.example.com'

    def test_connect_and_webhooks(self):
        with mock_woo(self.connect_routes()) as fake:
            self.store.action_woo_connect()
        self.assertEqual(self.store.state, 'connected')
        self.assertEqual(self.store.site_name, 'Demo Shop')
        self.assertEqual(self.store.site_currency_id.name, 'EUR')
        self.assertEqual(self.store.weight_unit, 'g')
        created = fake.bodies('POST webhooks')
        self.assertEqual(sorted(b['topic'] for b in created), sorted(self.store._woo_webhook_handlers()))
        self.assertTrue(all(b['delivery_url'] == self.store.webhook_url for b in created))
        self.assertTrue(all(b['secret'] == self.store.sudo().webhook_secret for b in created))
        self.assertEqual(len(self.store.webhook_ids), len(created))

    def test_sync_webhooks_reactivates_and_cleans(self):
        self.store.state = 'connected'
        url = self.store.webhook_url
        existing = [
            {'id': 1, 'topic': 'order.updated', 'delivery_url': url, 'status': 'disabled'},
            {'id': 2, 'topic': 'order.updated', 'delivery_url': url, 'status': 'active'},
            {'id': 3, 'topic': 'subscription.created', 'delivery_url': url, 'status': 'active'},
            {'id': 4, 'topic': 'order.created', 'delivery_url': 'https://other.example.com', 'status': 'active'},
        ]
        routes = self.connect_routes(**{
            'GET webhooks': existing,
            'PUT webhooks/1': lambda params, body: {'id': 1, 'topic': 'order.updated', 'delivery_url': url, **body},
            'DELETE webhooks/2': {'id': 2},
            'DELETE webhooks/3': {'id': 3},
        })
        with mock_woo(routes) as fake:
            self.store.action_woo_sync_webhooks()
        self.assertEqual(fake.bodies('PUT webhooks/1')[0]['status'], 'active')
        self.assertIn('DELETE webhooks/2', fake.paths())
        self.assertIn('DELETE webhooks/3', fake.paths(), "a topic no module handles")
        self.assertNotIn('DELETE webhooks/4', fake.paths(), "another address is not ours")
        self.assertNotIn('order.updated', [b['topic'] for b in fake.bodies('POST webhooks')])

    def test_plain_permalinks_found(self):
        routes = self.connect_routes()
        index = routes['GET /']
        for key in list(routes):
            if key.startswith('GET settings'):
                answer = routes[key]
                routes[key] = lambda params, body, answer=answer: answer if 'rest_route' in params else (404, '')
        routes['GET /'] = lambda params, body: index if 'rest_route' in params else (404, '<html>Not found</html>')
        with mock_woo(routes):
            self.store.action_woo_connect()
        self.assertEqual(self.store.state, 'connected')
        self.assertTrue(self.store.rest_route, "the API is reached through ?rest_route=")

    def test_wrong_key(self):
        routes = self.connect_routes(**{'GET settings/general/woocommerce_currency': (
            401, {'code': 'woocommerce_rest_cannot_view', 'message': 'Sorry, you cannot list resources.'})})
        with mock_woo(routes):
            self.store.action_woo_connect()
        self.assertEqual(self.store.state, 'error')
        self.assertIn('Sorry', self.store.last_error)
