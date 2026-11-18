import base64
import hashlib
import hmac
import json

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestWebhook(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store = cls.env['om.woocommerce.store'].create({
            'name': 'Demo', 'site_url': 'https://shop.example.com', 'consumer_key': 'ck', 'consumer_secret': 'cs'})
        cls.Job = cls.env['om.connector.job']

    def post(self, body, topic='order.updated', secret=None, store=None, headers=None):
        secret = secret or self.store.sudo().webhook_secret
        signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
        return self.url_open(f'/om_woocommerce/webhook/{(store or self.store).id}', data=body, headers={
            'X-WC-Webhook-Topic': topic, 'X-WC-Webhook-Signature': signature, 'X-WC-Webhook-Delivery-ID': 'd1',
            'Content-Type': 'application/json', **(headers or {})})

    def jobs(self):
        return self.Job.search([('backend_model', '=', 'om.woocommerce.store'), ('backend_id', '=', self.store.id)])

    def test_signed_webhook_is_queued_once(self):
        body = json.dumps({'id': 1001, 'status': 'processing'}).encode()
        self.assertEqual(self.post(body).status_code, 200)
        self.assertEqual(self.post(body).status_code, 200)
        jobs = self.jobs()
        self.assertEqual(len(jobs), 1, "sent twice: one job")
        self.assertEqual(jobs.method_name, '_connector_job_woo_order_webhook')
        self.assertEqual(jobs.payload['id'], 1001)

    def test_wrong_signature(self):
        body = json.dumps({'id': 1}).encode()
        self.assertEqual(self.post(body, secret='not-the-secret').status_code, 401)
        self.assertFalse(self.jobs())

    def test_ping_and_unknown(self):
        response = self.url_open(f'/om_woocommerce/webhook/{self.store.id}', data=b'webhook_id=12',
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(response.status_code, 200, "the ping of a new webhook is answered")
        self.assertFalse(self.jobs())
        self.assertEqual(self.post(json.dumps({'id': 1}).encode(), topic='subscription.created').status_code, 200)
        self.assertFalse(self.jobs(), "a topic no module handles is ignored")
        response = self.url_open('/om_woocommerce/webhook/999999', data=b'{}')
        self.assertEqual(response.status_code, 404)
