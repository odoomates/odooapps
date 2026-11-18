from urllib.parse import parse_qs, urlparse

from odoo.tests import tagged

from .common import INDEX, item, mock_woo, order
from .test_order import WooOrderCase


@tagged('post_install', '-at_install')
class TestCouponsAndAuthorize(WooOrderCase):

    def test_coupons_both_ways(self):
        job = self.store._connector_enqueue('_connector_job_woo_fetch_coupons')
        data = {'id': 300, 'code': 'SUMMER10', 'amount': '10.00', 'discount_type': 'percent', 'usage_count': 3,
                'product_ids': [10], 'date_expires_gmt': '2026-12-31T23:59:59'}
        with mock_woo({'GET coupons': [data]}):
            job.action_run_now()
        summer = self.env['om.woocommerce.coupon'].search([('code', '=', 'summer10')])
        self.assertEqual((summer.woo_id, summer.amount, summer.product_ids), ('300', 10.0, self.mug))
        sale = self._sync(order(order_id=3001, items=[item(1, 10, 1, 10, 9)], total=9,
                                coupon_lines=[{'id': 4, 'code': 'SUMMER10', 'discount': '1.00'}]))
        self.assertEqual(sale.woo_coupon_ids, summer)
        summer.amount = 15
        with mock_woo({'PUT coupons/300': lambda params, body: {'id': 300, **body}}) as fake:
            summer.action_woo_export()
        self.assertEqual(fake.bodies('PUT coupons/300')[0]['amount'], '15.00')
        # a deletion after an update archives it
        with mock_woo({}):
            self.store._woo_receive_webhook('coupon.updated', dict(data, amount='20.00')).action_run_now()
            self.store._woo_receive_webhook('coupon.deleted', {'id': 300}).action_run_now()
        self.assertFalse(summer.active)

    def test_approve_in_wordpress(self):
        self.store.write({'state': 'draft', 'consumer_key': False, 'consumer_secret': False})
        query = {k: v[0] for k, v in parse_qs(urlparse(self.store._woo_authorize_url()).query).items()}
        Store = self.env['om.woocommerce.store']
        self.assertFalse(Store._woo_auth_callback({'user_id': 'wrong', 'consumer_key': 'ck', 'consumer_secret': 'cs'}))
        Store._woo_auth_callback({'user_id': query['user_id'], 'consumer_key': 'ck_new', 'consumer_secret': 'cs_new'})
        self.assertEqual(self.store.sudo().consumer_key, 'ck_new')
        self.store.sudo().setup_pending = 'products'
        routes = {
            'GET /': INDEX,
            'GET settings/general/woocommerce_currency': {'value': 'USD'},
            'GET settings/products/woocommerce_weight_unit': {'value': 'kg'},
            'GET webhooks': [],
            'POST webhooks': lambda params, body: {'id': 1, 'status': 'active', **body},
        }
        with mock_woo(routes):
            self.store._woo_auth_return({'success': '1'})
        self.assertEqual(self.store.state, 'connected')
        self.assertIn('_connector_job_woo_fetch_products', self.env['om.connector.job'].search(
            [('backend_model', '=', self.store._name), ('backend_id', '=', self.store.id)]).mapped('method_name'))
