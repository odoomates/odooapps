from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import LOCATIONS_ANSWER, SHOP_ANSWER, ShopifyCase, mock_shopify

WEBHOOK_URI = 'https://odoo.example.com/om_shopify/webhook/%s'


@tagged('post_install', '-at_install')
class TestStore(ShopifyCase):

    def test_domain(self):
        self.assertEqual(self.store.shop_domain, 'demo-shop.myshopify.com')
        with self.assertRaises(ValidationError):
            self.store.shop_domain = 'not a shop!'

    def _webhooks(self, existing):
        return {
            'OmShopifyWebhooks': {'data': {'webhookSubscriptions': {
                'nodes': existing, 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}},
            'OmShopifyWebhookCreate': lambda v: {'data': {'webhookSubscriptionCreate': {
                'webhookSubscription': {'id': f"gid://shopify/WebhookSubscription/{v['topic']}",
                                        'topic': v['topic'], 'uri': v['uri']},
                'userErrors': []}}},
            'OmShopifyWebhookDelete': lambda v: {'data': {'webhookSubscriptionDelete': {
                'deletedWebhookSubscriptionId': v['id'], 'userErrors': []}}},
        }

    def test_connect_reads_shop_and_subscribes(self):
        uri = WEBHOOK_URI % self.store.id
        answers = {'OmShopifyShop': SHOP_ANSWER, 'OmShopifyLocations': LOCATIONS_ANSWER, **self._webhooks([
            {'id': 'gid://old', 'topic': 'CARTS_UPDATE', 'uri': uri},      # not handled anymore
            {'id': 'gid://other-app', 'topic': 'ORDERS_CREATE', 'uri': 'https://elsewhere'},  # not ours
        ])}
        with mock_shopify(answers) as fake:
            self.store.action_shopify_connect()
        self.assertEqual(self.store.state, 'connected')
        self.assertEqual(self.store.shop_name, 'Demo Shop')
        self.assertEqual(self.store.shop_currency_id.name, 'USD')
        self.assertIn('ORDERS_CREATE', self.store.webhook_ids.mapped('topic'))
        self.assertIn('APP_UNINSTALLED', self.store.webhook_ids.mapped('topic'))
        location = self.store.location_ids
        self.assertEqual(location.mapped('name'), ['Main Warehouse', 'Old Shop'])
        self.assertEqual(location[0].warehouse_id, self.store.warehouse_id, "the first active location gets the warehouse")
        self.assertFalse(location[1].warehouse_id)
        deleted = [c[1]['id'] for c in fake.calls if c[0] == 'OmShopifyWebhookDelete']
        self.assertEqual(deleted, ['gid://old'], "only the stale webhooks of Odoo are removed")

    def test_connect_error_is_kept(self):
        with mock_shopify({'OmShopifyShop': (401, {'errors': 'Invalid API key or access token'})}):
            action = self.store.action_shopify_connect()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(self.store.state, 'error')
        self.assertIn('refused', self.store.last_error)

    def test_no_webhooks_without_https(self):
        self.store.webhook_base_url = 'http://localhost:8069'
        with mock_shopify({'OmShopifyShop': SHOP_ANSWER, 'OmShopifyLocations': LOCATIONS_ANSWER}) as fake:
            self.store.action_shopify_connect()
        self.assertEqual(fake.names(), ['OmShopifyShop', 'OmShopifyLocations'])
        with self.assertRaises(UserError):
            self.store.action_shopify_sync_webhooks()

    def test_client_credentials_token_and_refresh(self):
        store = self.store
        store.write({'auth_type': 'client_credentials', 'client_id': 'cid', 'client_secret': 'csecret',
                     'webhook_base_url': False})
        self.assertFalse(store.access_token, "changing the credentials drops the old token")
        answers = {'OmShopifyShop': [(401, {'errors': 'expired'}), SHOP_ANSWER], 'OmShopifyLocations': LOCATIONS_ANSWER}
        with mock_shopify(answers, token={'access_token': 'shpat_fresh', 'expires_in': 86399}) as fake:
            store.action_shopify_connect()
        self.assertEqual(store.state, 'connected')
        self.assertEqual(fake.names(), ['token', 'OmShopifyShop', 'token', 'OmShopifyShop', 'OmShopifyLocations'],
                         "a refused token is renewed once")
        self.assertEqual(store.access_token, 'shpat_fresh')
        self.assertTrue(store.token_expires_at)
        with mock_shopify({'OmShopifyShop': SHOP_ANSWER, 'OmShopifyLocations': LOCATIONS_ANSWER}) as fake:
            store.action_shopify_connect()
        self.assertEqual(fake.names(), ['OmShopifyShop', 'OmShopifyLocations'], "a valid token is used again")


@tagged('post_install', '-at_install')
class TestSetupWizard(ShopifyCase):

    def test_three_steps(self):
        journal = self.env['account.journal'].create({'name': 'Shop Bank', 'type': 'bank', 'code': 'SHB'})
        wizard = self.env['om.shopify.setup.wizard'].create({
            'shop_domain': 'https://New-Shop.myshopify.com/admin', 'auth_type': 'token', 'access_token': 'shpat_x',
            'client_secret': 'sec'})
        with mock_shopify({'OmShopifyShop': SHOP_ANSWER, 'OmShopifyLocations': LOCATIONS_ANSWER}):
            wizard.action_connect()
        self.assertEqual(wizard.step, 'settings')
        store = wizard.store_id
        self.assertEqual((store.shop_domain, store.state), ('new-shop.myshopify.com', 'connected'))
        wizard.journal_id = journal
        wizard.action_settings()
        self.assertEqual(store.workflow_id.journal_id, journal)
        self.assertTrue(store.workflow_id.register_payment)
        wizard.action_finish()
        jobs = self.env['om.connector.job'].search(store._connector_job_domain())
        self.assertEqual(sorted(jobs.mapped('method_name')),
                         ['_connector_job_shopify_bulk_products', '_connector_job_shopify_fetch_orders'])


@tagged('post_install', '-at_install')
class TestSecrets(ShopifyCase):

    def test_secrets_are_encrypted(self):
        self.assertEqual(self.store.access_token, 'shpat_test')
        stored = self.store.sudo().access_token_encrypted
        self.assertTrue(stored.startswith('enc1:'))
        self.env.flush_all()
        self.env.cr.execute("SELECT access_token_encrypted, client_secret_encrypted FROM om_shopify_store WHERE id = %s",
                            [self.store.id])
        raw = ' '.join(self.env.cr.fetchone())
        self.assertNotIn('shpat_test', raw)
        self.assertNotIn('webhook-secret', raw)
        self.store.client_secret = 'new-secret'
        self.store.invalidate_recordset()
        self.assertEqual(self.store.client_secret, 'new-secret')
