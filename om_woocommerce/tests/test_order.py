from odoo.tests import tagged

from .common import WooCase, item, mock_woo, order, tax_line


class WooOrderCase(WooCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.state = 'connected'
        cls.mug = cls.env['product.product'].create({
            'name': 'Mug', 'default_code': 'MUG-1', 'list_price': 10.0, 'invoice_policy': 'order',
            'taxes_id': False, 'is_storable': True})
        template = cls.env['om.woocommerce.product.template'].create({
            'store_id': cls.store.id, 'external_id': '10', 'product_tmpl_id': cls.mug.product_tmpl_id.id,
            'name': 'Mug', 'woo_type': 'simple'})
        cls.mug_binding = cls.env['om.woocommerce.product'].create({
            'store_id': cls.store.id, 'external_id': '10', 'product_id': cls.mug.id,
            'template_binding_id': template.id, 'manage_stock': True})
        cls.SaleOrder = cls.env['sale.order']

    def _sync(self, data, routes=None):
        with mock_woo({f"GET orders/{data['id']}": data, **(routes or {})}) as fake:
            result = self.SaleOrder._woo_sync_order(self.store, data['id'])
        self.fake = fake
        return result


@tagged('post_install', '-at_install')
class TestOrderImport(WooOrderCase):

    def test_paid_order_is_confirmed_invoiced_and_paid(self):
        data = order(items=[item(1, 10, 2, 20, 16, taxes=[(1, 1.6)])],
                     shipping=[{'id': 2, 'method_title': 'Flat rate', 'method_id': 'flat_rate', 'total': '5.00',
                                'total_tax': '0.50', 'taxes': [{'id': 1, 'total': '0.50'}]}],
                     fees=[{'id': 3, 'name': 'Gift wrap', 'total': '2.00', 'total_tax': '0', 'taxes': []}],
                     tax_lines=[tax_line(1, 10.0, 'State Tax')], total=16 + 1.6 + 5 + 0.5 + 2,
                     coupon_lines=[{'id': 4, 'code': 'save20', 'discount': '4.00'}])
        sale = self._sync(data)
        self.assertEqual(sale.client_order_ref, '#1001')
        self.assertEqual(sale.partner_id.email, 'jane@example.com')
        self.assertEqual(sale.state, 'sale')
        line = sale.order_line.filtered(lambda l: l.product_id == self.mug)
        self.assertEqual(line.product_uom_qty, 2)
        self.assertEqual(line.price_unit, 10.0)
        self.assertAlmostEqual(line.discount, 20.0)
        self.assertEqual(line.tax_id.amount, 10.0, "a tax of the WooCommerce rate")
        self.assertFalse(line.tax_id.price_include)
        shipping = sale.order_line.filtered('is_delivery')
        self.assertEqual((shipping.price_unit, shipping.tax_id.amount), (5.0, 10.0))
        self.assertEqual(sale.order_line.filtered(lambda l: l.product_id == self.store.fee_product_id).price_unit, 2.0)
        self.assertEqual(sale.amount_total, 25.1)
        self.assertIn('coupon:save20', sale.tag_ids.mapped('name'))
        self.assertEqual(sale.woo_gateway_id.name, 'stripe')
        invoice = sale.invoice_ids
        self.assertEqual(invoice.state, 'posted')
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertFalse(sale.message_ids.filtered(lambda m: 'is not the total' in (m.body or '')))

    def test_prices_including_taxes(self):
        data = order(items=[item(1, 10, 1, 18.18, taxes=[(2, 1.82)])], include_tax=True,
                     tax_lines=[tax_line(2, 10.0, 'VAT')], total=20.0)
        sale = self._sync(data)
        line = sale.order_line
        self.assertAlmostEqual(line.price_unit, 20.0)
        self.assertTrue(line.tax_id.price_include)
        self.assertAlmostEqual(sale.amount_total, 20.0)

    def test_guest_order_and_idempotent(self):
        jane = self.env['res.partner'].create({'name': 'Jane D.', 'email': 'JANE@example.com'})
        data = order(items=[item(1, 10, 1, 10)], total=10)
        sale = self._sync(data)
        self.assertEqual(sale.partner_id, jane, "a guest is found by email")
        self.assertEqual(self._sync(data), sale, "imported once")
        self.assertEqual(self.SaleOrder.search_count([('woo_store_id', '=', self.store.id)]), 1)

    def test_statuses(self):
        result = self._sync(order(status='pending', paid=False, items=[item(1, 10, 1, 10)], total=10))
        self.assertIsInstance(result, str, "a pending order is not paid yet: not imported")
        data = order(order_id=1002, status='on-hold', paid=False, method='bacs', items=[item(1, 10, 1, 10)], total=10)
        sale = self._sync(data)
        self.assertEqual(sale.state, 'sale')
        self.assertEqual(sale.invoice_ids.payment_state, 'not_paid', "on hold: waiting for the bank transfer")
        sale = self._sync(dict(data, status='processing', date_paid_gmt='2026-11-17T10:00:00'))
        self.assertTrue(sale.woo_paid)
        self.assertIn(sale.invoice_ids.payment_state, ('paid', 'in_payment'))

    def test_completed_order_is_delivered_once(self):
        sale = self._sync(order(status='completed', items=[item(1, 10, 1, 10)], total=10))
        self.assertEqual(sale.picking_ids.state, 'done', "completed before the import: delivered in Odoo")
        self.assertFalse(self.env['om.connector.job'].search([('method_name', '=', '_connector_job_woo_complete')]),
                         "and not completed again in WooCommerce")

    def test_cancelled(self):
        data = order(status='on-hold', paid=False, items=[item(1, 10, 1, 10)], total=10)
        sale = self._sync(data)
        sale = self._sync(dict(data, status='cancelled'))
        self.assertEqual(sale.state, 'cancel')
        self.assertTrue(sale.woo_cancelled)

    def test_unknown_product_and_total(self):
        data = order(items=[item(1, 999, 1, 10, sku='GONE')], total=12)
        sale = self._sync(data, {'GET products/999': (404, {'code': 'woocommerce_rest_product_invalid_id'})})
        self.assertEqual(sale.order_line.product_id, self.store.custom_product_id)
        self.assertTrue(sale.message_ids.filtered(lambda m: 'is not the total' in (m.body or '')))

    def test_rules_currency_and_number(self):
        cod = self.store.workflow_id.copy({'name': 'Cash on delivery', 'register_payment': False})
        shop = self.env['stock.warehouse'].create({'name': 'Shop', 'code': 'SHOP'})
        gateway = self.env['om.woocommerce.gateway']._woo_get(self.store, 'cod', 'Cash on delivery')
        self.env['om.woocommerce.order.rule'].create([
            {'store_id': self.store.id, 'gateway_id': gateway.id, 'workflow_id': cod.id, 'sequence': 1},
            {'store_id': self.store.id, 'shipping_method': 'local_pickup', 'warehouse_id': shop.id, 'sequence': 2},
        ])
        self.store.write({'order_use_woo_number': True, 'order_prefix': 'WC'})
        data = order(method='cod', paid=False, items=[item(1, 10, 1, 10)], total=10, currency='EUR',
                     shipping=[{'id': 2, 'method_title': 'Pickup', 'method_id': 'local_pickup', 'total': '0',
                                'taxes': []}])
        data['currency'] = 'EUR'
        sale = self._sync(data)
        self.assertEqual(sale.woo_workflow_id, cod)
        self.assertEqual(sale.warehouse_id, shop)
        self.assertEqual(sale.name, 'WC1001')
        self.assertEqual(sale.currency_id.name, 'EUR')
        self.assertEqual(gateway.title, 'Cash on delivery')


@tagged('post_install', '-at_install')
class TestOrderJobs(WooOrderCase):

    def test_fetch_orders_queues_what_matters(self):
        known = self._sync(order(order_id=3, items=[item(1, 10, 1, 10)], total=10))
        listing = [{'id': 1, 'number': '1', 'status': 'processing'}, {'id': 2, 'number': '2', 'status': 'pending'},
                   {'id': 3, 'number': '3', 'status': 'cancelled'}]
        job = self.store._connector_enqueue('_connector_job_woo_fetch_orders')
        with mock_woo({'GET orders': listing}) as fake:
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(fake.calls[0][2]['status'], 'any')
        self.assertIn('modified_after', fake.calls[0][2])
        queued = self.env['om.connector.job'].search([('method_name', '=', '_connector_job_woo_import_order')])
        self.assertEqual(sorted(j.payload['id'] for j in queued), [1, 3],
                         "the orders to import, and the cancelled one imported before")
        self.assertTrue(known)

    def test_import_by_number(self):
        wizard = self.env['om.woocommerce.import.wizard'].create({
            'store_id': self.store.id, 'kind': 'order', 'references': '#1001'})
        data = order(items=[item(1, 10, 1, 10)], total=10)
        with mock_woo({'GET orders/1001': data}):
            wizard.action_import()
        self.assertTrue(self.SaleOrder.search([('woo_order_id', '=', '1001')]))
