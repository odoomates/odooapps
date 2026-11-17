from odoo.tests import tagged

from .common import ShopifyCase, line, mock_shopify, money, order


@tagged('post_install', '-at_install')
class TestOrderImport(ShopifyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.state = 'connected'
        cls.mug = cls.env['product.product'].create({
            'name': 'Mug', 'default_code': 'MUG-1', 'list_price': 10.0, 'invoice_policy': 'order', 'taxes_id': False})
        template = cls.env['om.shopify.product.template'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/Product/1', 'product_tmpl_id': cls.mug.product_tmpl_id.id})
        cls.env['om.shopify.product'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/ProductVariant/11', 'product_id': cls.mug.id,
            'template_binding_id': template.id, 'inventory_item_gid': 'gid://shopify/InventoryItem/11', 'tracked': True})
        cls.SaleOrder = cls.env['sale.order']

    def _sync(self, answer, gid='gid://shopify/Order/1001'):
        with mock_shopify({'OmShopifyOrder': answer}):
            return self.SaleOrder._shopify_sync_order(self.store, gid)

    def test_paid_order_is_confirmed_invoiced_and_paid(self):
        shipping = [{'title': 'Standard', 'code': 'STD', 'source': 'shopify', 'originalPriceSet': money(5),
                     'discountAllocations': [], 'taxLines': [{'title': 'State Tax', 'rate': 0.1, 'priceSet': money(0.5)}]}]
        data = order(lines=[line(1, 11, 1, 2, 10, discount=4, taxes=[('State Tax', 0.1)])],
                     shipping=shipping, tip=2, total=2 * 10 - 4 + 1.6 + 5 + 0.5 + 2)
        sale = self._sync(data)
        self.assertEqual(sale.shopify_order_name, '#1001')
        self.assertEqual(sale.client_order_ref, '#1001')
        self.assertEqual(sale.partner_id.email, 'jane@example.com')
        self.assertEqual(sale.state, 'sale')
        product_line = sale.order_line.filtered(lambda l: l.product_id == self.mug)
        self.assertEqual(product_line.product_uom_qty, 2)
        self.assertAlmostEqual(product_line.discount, 20.0)
        self.assertEqual(product_line.tax_ids.amount, 10.0, "a tax of the Shopify rate")
        self.assertTrue(sale.order_line.filtered('is_delivery'))
        self.assertEqual(sale.amount_total, 25.1)
        self.assertFalse(sale.message_ids.filtered(lambda m: 'not the total' in (m.body or '')),
                         "the total is the one of Shopify")
        invoice = sale.invoice_ids
        self.assertEqual(invoice.state, 'posted')
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertEqual(sale.shopify_gateway_id.name, 'bogus')

    def test_import_is_idempotent_and_partner_reused(self):
        data = order(lines=[line(1, 11, 1, 1, 10)], total=10)
        first = self._sync(data)
        again = self._sync(data)
        self.assertEqual(first, again)
        other = self._sync(order(gid=1002, name='#1002', lines=[line(2, 11, 1, 1, 10)], total=10),
                           gid='gid://shopify/Order/1002')
        self.assertEqual(other.partner_id, first.partner_id, "the Shopify customer is linked once")

    def test_pending_order_is_not_paid_then_paid(self):
        sale = self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10, financial='PENDING'))
        self.assertEqual(sale.invoice_ids.payment_state, 'not_paid')
        self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10, financial='PAID'))
        self.assertIn(sale.invoice_ids.payment_state, ('paid', 'in_payment'))

    def test_cancelled_order(self):
        self.store.workflow_id.write({'create_invoice': False, 'register_payment': False})
        sale = self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10, financial='PENDING'))
        self.assertEqual(sale.state, 'sale')
        self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10, cancelled=True))
        self.assertEqual(sale.state, 'cancel')
        self.assertEqual(self._sync(order(gid=1003, name='#1003', lines=[line(3, 11, 1, 1, 10)], cancelled=True),
                                    gid='gid://shopify/Order/1003'), '#1003 is cancelled: skipped')

    def test_custom_item_and_unknown_product_import(self):
        product_answer = {'data': {'product': {
            'id': 'gid://shopify/Product/9', 'title': 'Poster', 'handle': 'poster', 'status': 'ACTIVE',
            'descriptionHtml': '', 'vendor': '', 'productType': '', 'tags': [], 'updatedAt': 'x',
            'options': [{'name': 'Title', 'position': 1, 'optionValues': [{'name': 'Default Title'}]}],
            'featuredMedia': None,
            'variants': {'nodes': [{'id': 'gid://shopify/ProductVariant/99', 'title': 'Default Title', 'sku': 'POSTER',
                                    'barcode': None, 'price': '8.00', 'compareAtPrice': None, 'position': 1,
                                    'selectedOptions': [{'name': 'Title', 'value': 'Default Title'}],
                                    'inventoryItem': {'id': 'gid://shopify/InventoryItem/99', 'tracked': False,
                                                      'measurement': {'weight': None}}}],
                         'pageInfo': {'hasNextPage': False}}}}}
        data = order(lines=[line(1, 99, 9, 1, 8), line(2, None, None, 1, 3, name='Engraving')], total=11)
        with mock_shopify({'OmShopifyOrder': data, 'OmShopifyProduct': product_answer}):
            sale = self.SaleOrder._shopify_sync_order(self.store, 'gid://shopify/Order/1001')
        self.assertEqual(sorted(sale.order_line.product_id.mapped('name')), ['Custom Item (Shopify)', 'Poster'])

    def test_taxes_included(self):
        data = order(lines=[line(1, 11, 1, 1, 12, taxes=[('VAT', 0.2)])], taxes_included=True, total=12)
        sale = self._sync(data)
        self.assertTrue(sale.order_line.tax_ids.price_include)
        self.assertEqual(sale.amount_total, 12.0)
        self.assertEqual(sale.amount_tax, 2.0)

    def test_order_webhook_and_fetch_job(self):
        ids = {'data': {'orders': {'nodes': [{'id': 'gid://shopify/Order/1001', 'name': '#1001', 'updatedAt': 'x'}],
                                   'pageInfo': {'hasNextPage': False, 'endCursor': None}}}}
        job = self.store._connector_enqueue('_connector_job_shopify_fetch_orders')
        with mock_shopify({'OmShopifyOrderIds': ids}):
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        order_job = self.env['om.connector.job'].search([('dedupe_key', '=', 'order:gid://shopify/Order/1001')])
        with mock_shopify({'OmShopifyOrder': order(lines=[line(1, 11, 1, 1, 10)], total=10)}):
            order_job._run()
        self.assertEqual(order_job.state, 'done', order_job.error)
        self.assertEqual(order_job.record_name and order_job._get_record().shopify_order_name, '#1001')
