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
        cls.store = cls.env['om.shopify.store'].create({
            'name': 'Demo', 'shop_domain': 'demo-shop.myshopify.com', 'auth_type': 'token',
            'access_token': 'shpat_test', 'client_secret': 'webhook-secret',
        })
        cls.Job = cls.env['om.connector.job']

    def _post(self, payload, topic='app/uninstalled', webhook_id='w1', secret='webhook-secret',
              shop='demo-shop.myshopify.com'):
        body = json.dumps(payload).encode()
        signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
        return self.url_open(f'/om_shopify/webhook/{self.store.id}', data=body, headers={
            'Content-Type': 'application/json', 'X-Shopify-Hmac-Sha256': signature, 'X-Shopify-Topic': topic,
            'X-Shopify-Shop-Domain': shop, 'X-Shopify-Webhook-Id': webhook_id,
        })

    def _jobs(self):
        return self.Job.search([('backend_model', '=', 'om.shopify.store'), ('backend_id', '=', self.store.id)])

    def test_signed_webhook_is_queued_once(self):
        response = self._post({'id': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._post({'id': 1}).status_code, 200, "Shopify sends a webhook again: still 200")
        job = self._jobs()
        self.assertEqual(len(job), 1)
        self.assertEqual(job.payload, {'id': 1})
        self.assertEqual(job.method_name, '_connector_job_shopify_app_uninstalled')
        job._run()
        self.assertEqual(job.state, 'done')
        self.assertEqual(self.store.state, 'error')
        self.assertFalse(self.store.access_token)

    def test_wrong_signature_or_shop(self):
        with self.assertLogs('odoo.addons.om_shopify.controllers.webhook', 'WARNING') as logs:
            self.assertEqual(self._post({'id': 1}, secret='forged').status_code, 401)
            self.assertEqual(self._post({'id': 1}, shop='other.myshopify.com').status_code, 401)
        self.assertEqual(len(logs.records), 2, "each refused webhook is logged")
        self.assertFalse(self._jobs())

    def test_unhandled_topic_is_ignored(self):
        self.assertEqual(self._post({'id': 1}, topic='carts/update').status_code, 200)
        self.assertFalse(self._jobs())

    def test_unknown_store(self):
        response = self.url_open('/om_shopify/webhook/999999', data=b'{}',
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 404)

    def test_gdpr_webhooks(self):
        partner = self.env['res.partner'].create({'name': 'Jane Doe', 'email': 'jane@example.com', 'city': 'Austin'})
        self.env['om.shopify.customer'].create({'store_id': self.store.id, 'external_id': 'gid://shopify/Customer/7',
                                                'partner_id': partner.id})
        old = self.store._connector_enqueue('_connector_job_shopify_app_uninstalled', {'email': 'jane@example.com'})
        old.state = 'done'
        customer = {'id': 7, 'email': 'jane@example.com', 'phone': None}
        self.assertEqual(self._post({'customer': customer, 'orders_requested': [], 'data_request': {'id': 9}},
                                    topic='customers/data_request', webhook_id='g1').status_code, 200)
        self.assertEqual(self._post({'customer': customer, 'orders_to_redact': []},
                                    topic='customers/redact', webhook_id='g2').status_code, 200)
        jobs = self._jobs().filtered(lambda j: j.method_name.startswith('_connector_job_shopify_gdpr'))
        self.assertEqual(len(jobs), 2)
        for job in jobs.sorted('id'):
            job._run()
            self.assertEqual(job.state, 'done', job.error)
        self.assertFalse(old.payload, "the Shopify data of the customer is removed from the jobs")
        self.assertFalse(self.env['om.shopify.customer'].search([('partner_id', '=', partner.id)]))
        summaries = self.store.activity_ids.mapped('summary')
        self.assertIn('GDPR: data request', summaries)
        self.assertIn('GDPR: erase a customer', summaries)
        self.assertEqual(partner.city, 'Austin', "not anonymized unless the store says so")
        # anonymize, then erase the shop
        self.store.gdpr_anonymize = True
        self.env['om.shopify.customer'].create({'store_id': self.store.id, 'external_id': 'gid://shopify/Customer/7',
                                                'partner_id': partner.id})
        self._post({'customer': customer, 'orders_to_redact': []}, topic='customers/redact', webhook_id='g3')
        self._post({'shop_id': 1, 'shop_domain': 'demo-shop.myshopify.com'}, topic='shop/redact', webhook_id='g4')
        for job in self._jobs().filtered(lambda j: j.state == 'pending').sorted('id'):
            job._run()
            self.assertEqual(job.state, 'done', job.error)
        self.assertEqual((partner.name, partner.email, partner.active), ('Redacted customer', False, False))
        self.assertFalse(self.store.active)
        self.assertFalse(self.store.sudo().access_token_encrypted)
