from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools.binary import BinaryBytes

from .common import ShopifyCase, line, mock_shopify, money, order, product, variant

ORDER_GID = 'gid://shopify/Order/1001'


def _png():
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), (200, 0, 0)).save(buffer, format='PNG')
    return buffer.getvalue()


@tagged('post_install', '-at_install')
class TestOrderFeatures(ShopifyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.state = 'connected'
        cls.mug = cls.env['product.product'].create({
            'name': 'Mug', 'default_code': 'MUG-1', 'is_storable': True, 'invoice_policy': 'order', 'taxes_id': False})
        template = cls.env['om.shopify.product.template'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/Product/1', 'product_tmpl_id': cls.mug.product_tmpl_id.id})
        cls.env['om.shopify.product'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/ProductVariant/11', 'product_id': cls.mug.id,
            'template_binding_id': template.id, 'inventory_item_gid': 'gid://shopify/InventoryItem/11', 'tracked': True})
        cls.env['stock.quant']._update_available_quantity(cls.mug, cls.store.warehouse_id.lot_stock_id, 50)
        cls.SaleOrder = cls.env['sale.order']

    def _sync(self, answer, **answers):
        with mock_shopify({'OmShopifyOrder': answer, **answers}) as fake:
            result = self.SaleOrder._shopify_sync_order(self.store, ORDER_GID)
        return result, fake

    def _refund(self, gid='gid://shopify/Refund/1', qty=1, amount=10, restock='RETURN', shipping=0):
        return {
            'id': gid, 'createdAt': '2026-11-16T11:00:00Z', 'note': 'Broken',
            'totalRefundedSet': money(amount),
            'refundLineItems': {'nodes': [{'quantity': qty, 'restockType': restock,
                                           'lineItem': {'id': 'gid://shopify/LineItem/1'},
                                           'subtotalSet': money(10 * qty)}]},
            'refundShippingLines': {'nodes': [{'subtotalAmountSet': money(shipping)}] if shipping else []},
            'transactions': {'nodes': [{'kind': 'REFUND', 'status': 'SUCCESS', 'gateway': 'bogus',
                                        'amountSet': money(amount)}]},
        }

    def test_refund_becomes_paid_credit_note_and_return(self):
        self.store.write({'refund_create_return': True, 'refund_validate_return': True})
        sale, _fake = self._sync(order(lines=[line(1, 11, 1, 2, 10)], total=20))
        sale._shopify_deliver()
        refunded = order(lines=[line(1, 11, 1, 2, 10)], total=20, financial='PARTIALLY_REFUNDED',
                         refunds=[self._refund()])
        self._sync(refunded)
        credit_note = sale.invoice_ids.filtered(lambda m: m.move_type == 'out_refund')
        self.assertEqual(len(credit_note), 1)
        self.assertEqual(credit_note.amount_total, 10)
        self.assertEqual(credit_note.shopify_refund_gid, 'gid://shopify/Refund/1')
        self.assertIn(credit_note.payment_state, ('paid', 'in_payment'))
        returns = sale.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming')
        self.assertEqual(returns.state, 'done')
        self.assertEqual(returns.move_ids.quantity, 1)
        self._sync(refunded)
        self.assertEqual(len(sale.invoice_ids.filtered(lambda m: m.move_type == 'out_refund')), 1,
                         "a refund is imported once")

    def test_date_delivery_invoicing_and_refunded_quantities(self):
        self.mug.invoice_policy = 'delivery'
        data = order(lines=[line(1, 11, 1, 2, 10)], total=20, displayFulfillmentStatus='FULFILLED')
        sale, _fake = self._sync(data)
        self.assertEqual(sale.date_order.strftime('%Y-%m-%d %H:%M'), '2026-11-16 09:00', "the date of Shopify")
        self.assertEqual(sale.picking_ids.state, 'done')
        self.assertIn(sale.invoice_ids.payment_state, ('paid', 'in_payment'),
                      "invoiced and paid once delivered, for products invoiced on delivery")
        # a refund of what was not delivered leaves the order
        self.mug.invoice_policy = 'order'
        data = order(gid=1002, name='#1002', lines=[line(5, 11, 1, 2, 10)], total=20)
        with mock_shopify({'OmShopifyOrder': data}):
            sale2 = self.SaleOrder._shopify_sync_order(self.store, 'gid://shopify/Order/1002')
        refund = self._refund(qty=1, amount=10, restock='NO_RESTOCK')
        refund['refundLineItems']['nodes'][0]['lineItem']['id'] = 'gid://shopify/LineItem/5'
        data['data']['order']['refunds'] = [refund]
        data['data']['order']['lineItems']['nodes'][0]['currentQuantity'] = 1
        with mock_shopify({'OmShopifyOrder': data}):
            self.SaleOrder._shopify_sync_order(self.store, 'gid://shopify/Order/1002')
        self.assertEqual(sale2.order_line.filtered('shopify_line_gid').product_uom_qty, 1)
        self.assertNotEqual(sale2.invoice_status, 'to invoice')
        # refunded before being invoiced (invoiced on delivery): only an adjustment, the order stays right
        self.mug.invoice_policy = 'delivery'
        data = order(gid=1003, name='#1003', lines=[line(7, 11, 1, 2, 10)], total=20)
        with mock_shopify({'OmShopifyOrder': data}):
            sale3 = self.SaleOrder._shopify_sync_order(self.store, 'gid://shopify/Order/1003')
        refund = self._refund(gid='gid://shopify/Refund/3', qty=1, amount=10, restock='NO_RESTOCK')
        refund['refundLineItems']['nodes'][0]['lineItem']['id'] = 'gid://shopify/LineItem/7'
        data['data']['order']['refunds'] = [refund]
        data['data']['order']['lineItems']['nodes'][0]['currentQuantity'] = 1
        with mock_shopify({'OmShopifyOrder': data}):
            self.SaleOrder._shopify_sync_order(self.store, 'gid://shopify/Order/1003')
        self.assertFalse(self.env['account.move'].search([('shopify_refund_gid', '=', 'gid://shopify/Refund/3')]),
                         "nothing invoiced yet: no credit note")
        self.assertEqual(sale3.order_line.filtered('shopify_line_gid').product_uom_qty, 1)
        with mock_shopify({'OmShopifyOrder': data}):
            self.SaleOrder._shopify_sync_order(self.store, 'gid://shopify/Order/1003')
        self.assertEqual(sale3.order_line.filtered('shopify_line_gid').product_uom_qty, 1, "applied once")

    def test_refund_adjustment_line(self):
        sale, _fake = self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10))
        self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10, refunds=[self._refund(qty=0, amount=3)]))
        credit_note = self.env['account.move'].search([('shopify_refund_gid', '=', 'gid://shopify/Refund/1')])
        self.assertEqual(credit_note.amount_total, 3)
        self.assertEqual(credit_note.invoice_line_ids.product_id, self.store.refund_adjustment_product_id)

    def test_credit_note_refunded_in_shopify(self):
        sale, _fake = self._sync(order(lines=[line(1, 11, 1, 2, 10)], total=20))
        invoice = sale.invoice_ids
        reversal = self.env['account.move.reversal'].with_context(active_model='account.move', active_ids=invoice.ids)\
            .create({'journal_id': invoice.journal_id.id, 'reason': 'test'})
        credit_note = self.env['account.move'].browse(reversal.refund_moves()['res_id'])
        credit_note.invoice_line_ids.quantity = 1
        credit_note.action_post()
        self.assertEqual(credit_note.shopify_order_id, sale)
        credit_note.action_shopify_refund()
        job = self.env['om.connector.job'].search([('dedupe_key', '=', f'refund:{credit_note.id}')])
        suggested = {'data': {'order': {'suggestedRefund': {'amountSet': money(10), 'suggestedTransactions': [
            {'gateway': 'bogus', 'kind': 'SUGGESTED_REFUND', 'amountSet': money(20),
             'parentTransaction': {'id': 'gid://shopify/OrderTransaction/1'}}]}}}}
        created = {'data': {'refundCreate': {'refund': {'id': 'gid://shopify/Refund/9',
                                                        'totalRefundedSet': {'shopMoney': {'amount': '10.0'}}},
                                             'userErrors': []}}}
        with mock_shopify({'OmShopifySuggestedRefund': suggested, 'OmShopifyRefundCreate': created}) as fake:
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        refund_input = fake.calls[1][1]['input']
        self.assertEqual(refund_input['refundLineItems'], [{'lineItemId': 'gid://shopify/LineItem/1', 'quantity': 1,
                                                            'restockType': 'NO_RESTOCK'}])
        self.assertEqual(refund_input['transactions'][0]['amount'], '10.00')
        self.assertEqual(refund_input['transactions'][0]['parentId'], 'gid://shopify/OrderTransaction/1')
        self.assertTrue(fake.calls[1][1]['key'])
        self.assertEqual(credit_note.shopify_refund_gid, 'gid://shopify/Refund/9')

    def test_cancel_in_shopify(self):
        self.store.workflow_id.write({'create_invoice': False, 'register_payment': False})
        sale, _fake = self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10))
        wizard = self.env['om.shopify.cancel.wizard'].create({'order_id': sale.id, 'reason': 'INVENTORY'})
        answer = {'data': {'orderCancel': {'job': {'id': 'gid://shopify/Job/1', 'done': False},
                                           'orderCancelUserErrors': []}}}
        with mock_shopify({'OmShopifyOrderCancel': answer}) as fake:
            wizard.action_cancel()
        self.assertEqual(fake.calls[0][1]['reason'], 'INVENTORY')
        self.assertEqual(fake.calls[0][1]['refundMethod'], {'originalPaymentMethodsRefund': True})
        self.assertEqual(sale.state, 'cancel')
        self.assertTrue(sale.shopify_cancelled)

    def test_risky_order_waits(self):
        risk = {'recommendation': 'CANCEL', 'assessments': [{'riskLevel': 'HIGH', 'facts': [
            {'description': 'Card used many times'}]}]}
        data = order(lines=[line(1, 11, 1, 1, 10)], total=10, risk=risk)
        sale, _fake = self._sync(data)
        self.assertEqual(sale.state, 'draft')
        self.assertTrue(sale.shopify_on_hold)
        self.assertIn('Card used', sale.shopify_risk_message)
        self.assertTrue(sale.activity_ids)
        with mock_shopify({'OmShopifyOrder': data}):
            sale.action_shopify_release()
        self.assertEqual(sale.state, 'sale')
        self.assertIn(sale.invoice_ids.payment_state, ('paid', 'in_payment'))

    def test_two_payment_methods(self):
        gift_journal = self.env['account.journal'].create({'name': 'Gift Cards', 'type': 'bank', 'code': 'GIFT'})
        gift_workflow = self.store.workflow_id.copy({'name': 'Gift', 'journal_id': gift_journal.id})
        self.env['om.shopify.gateway'].create({'store_id': self.store.id, 'name': 'gift_card',
                                               'workflow_id': gift_workflow.id})
        transactions = [
            {'id': 't1', 'kind': 'SALE', 'status': 'SUCCESS', 'gateway': 'bogus', 'amountSet': money(15)},
            {'id': 't2', 'kind': 'SALE', 'status': 'SUCCESS', 'gateway': 'gift_card', 'amountSet': money(5)},
        ]
        data = order(lines=[line(1, 11, 1, 2, 10)], total=20, transactions=transactions,
                     paymentGatewayNames=['gift_card', 'bogus'])
        sale, _fake = self._sync(data)
        self.assertEqual(sale.shopify_gateway_id.name, 'bogus')
        payments = self.env['account.payment'].search([('partner_id', '=', sale.partner_id.commercial_partner_id.id)])
        self.assertEqual(sorted(payments.mapped(lambda p: (p.journal_id.code, p.amount))),
                         sorted([(self.store.workflow_id.journal_id.code, 15.0), ('GIFT', 5.0)]))
        self.assertIn(sale.invoice_ids.payment_state, ('paid', 'in_payment'))

    def test_duties_pos_and_fulfilled(self):
        pos = self.env['res.partner'].create({'name': 'Walk-in'})
        self.store.write({'pos_partner_id': pos.id})
        data = order(lines=[line(1, 11, 1, 1, 10)], total=13, currentTotalDutiesSet=money(3),
                     sourceName='pos', customer=None, displayFulfillmentStatus='FULFILLED')
        sale, fake = self._sync(data)
        self.assertEqual(sale.partner_id, pos)
        self.assertEqual(sale.amount_total, 13)
        self.assertIn(self.store.duties_product_id, sale.order_line.product_id)
        self.assertEqual(sale.picking_ids.state, 'done', "fulfilled before the import: delivered in Odoo")
        self.assertFalse(self.env['om.connector.job'].search([('method_name', '=', '_connector_job_shopify_fulfill')]),
                         "and not fulfilled again in Shopify")

    def test_rules_and_location_warehouse(self):
        prime = self.env['stock.warehouse'].create({'name': 'Prime', 'code': 'PRM'})
        cod = self.store.workflow_id.copy({'name': 'Cash on delivery', 'register_payment': False})
        self.env['om.shopify.order.rule'].create([
            {'store_id': self.store.id, 'tag': 'prime', 'warehouse_id': prime.id, 'sequence': 1},
            {'store_id': self.store.id, 'financial_status': 'PENDING', 'workflow_id': cod.id, 'sequence': 2},
        ])
        sale, _fake = self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10, financial='PENDING', tags=['Prime']))
        self.assertEqual(sale.warehouse_id, prime)
        self.assertEqual(sale.shopify_workflow_id, cod)
        # from the location
        other = self.env['stock.warehouse'].create({'name': 'Second', 'code': 'SEC'})
        self.env['om.shopify.location'].create({'store_id': self.store.id, 'name': 'L2', 'shopify_gid': 'loc2',
                                                'warehouse_id': other.id, 'shopify_active': True})
        self.store.order_warehouse_from_location = True
        data = order(gid=1002, name='#1002', lines=[line(2, 11, 1, 1, 10)], total=10,
                     fulfillmentOrders={'nodes': [{'status': 'OPEN', 'assignedLocation': {'location': {'id': 'loc2'}}}]})
        with mock_shopify({'OmShopifyOrder': data}):
            sale2 = self.SaleOrder._shopify_sync_order(self.store, 'gid://shopify/Order/1002')
        self.assertEqual(sale2.warehouse_id, other)

    def test_order_edits(self):
        self.store.workflow_id.write({'create_invoice': False, 'register_payment': False})
        sale, _fake = self._sync(order(lines=[line(1, 11, 1, 1, 10)], total=10, financial='PENDING'))
        edited = order(lines=[line(1, 11, 1, 3, 10), line(2, 11, 1, 1, 10, name='Extra mug')], total=40,
                       financial='PENDING')
        self._sync(edited)
        self.assertEqual(sorted(sale.order_line.mapped('product_uom_qty')), [1.0, 3.0])
        self.assertTrue(sale.message_ids.filtered(lambda m: 'Edited in Shopify' in (m.body or '')))

    def test_customer_currency(self):
        eur = self.env.ref('base.EUR')
        eur.active = True
        self.store.order_currency = 'customer'
        data = order(lines=[{**line(1, 11, 1, 1, 10), 'originalUnitPriceSet': money(10, presentment=9)}],
                     totalPriceSet=money(10, presentment=9), presentmentCurrencyCode='EUR',
                     transactions=[{'id': 't', 'kind': 'SALE', 'status': 'SUCCESS', 'gateway': 'bogus',
                                    'amountSet': money(10, presentment=9)}])
        sale, _fake = self._sync(data)
        self.assertEqual(sale.currency_id, eur)
        self.assertEqual(sale.amount_total, 9)


@tagged('post_install', '-at_install')
class TestProductFeatures(ShopifyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.state = 'connected'

    def test_export_product_with_variants(self):
        size = self.env['product.attribute'].create({'name': 'OmSize', 'value_ids': [
            (0, 0, {'name': 'S'}), (0, 0, {'name': 'M'})]})
        template = self.env['product.template'].create({
            'name': 'Hoodie', 'list_price': 30, 'is_storable': True, 'weight': 0.8,
            'attribute_line_ids': [(0, 0, {'attribute_id': size.id, 'value_ids': [(6, 0, size.value_ids.ids)]})]})
        for product in template.product_variant_ids:
            product.default_code = f"HOOD-{product.product_template_attribute_value_ids.name}"
        answer = lambda v: {'data': {'productSet': {'product': {  # noqa: E731
            'id': 'gid://shopify/Product/50', 'handle': 'hoodie', 'status': 'DRAFT',
            'variants': {'nodes': [
                {'id': f'gid://shopify/ProductVariant/5{i}', 'sku': var['inventoryItem']['sku'],
                 'selectedOptions': [{'name': o['optionName'], 'value': o['name']} for o in var['optionValues']],
                 'inventoryItem': {'id': f'gid://shopify/InventoryItem/5{i}', 'tracked': True}}
                for i, var in enumerate(v['input']['variants'])]}}, 'userErrors': []}}}
        with mock_shopify({'OmShopifyProductSet': answer}) as fake:
            binding = self.env['om.shopify.product.template']._shopify_export_product(self.store, template, images=False)
        product_input = fake.calls[0][1]['input']
        self.assertEqual(product_input['productOptions'][0]['name'], 'OmSize')
        self.assertEqual(len(product_input['variants']), 2)
        self.assertEqual(product_input['variants'][0]['price'], '30.00')
        self.assertEqual(product_input['status'], 'DRAFT')
        self.assertNotIn('identifier', fake.calls[0][1])
        self.assertEqual(len(binding.variant_ids), 2)
        self.assertEqual(sorted(binding.variant_ids.mapped('sku')), ['HOOD-M', 'HOOD-S'])
        # a second export updates the same product
        with mock_shopify({'OmShopifyProductSet': answer}) as fake:
            self.env['om.shopify.product.template']._shopify_export_product(self.store, template, images=False)
        self.assertEqual(fake.calls[0][1]['identifier'], {'id': 'gid://shopify/Product/50'})

    def test_export_image_and_publish(self):
        template = self.env['product.template'].create({
            'name': 'Cap', 'list_price': 12, 'default_code': 'CAP',
            'image_1920': BinaryBytes(_png())})
        self.store.product_publish = True
        staged = {'data': {'stagedUploadsCreate': {'stagedTargets': [{
            'url': 'https://uploads.example.com', 'resourceUrl': 'https://uploads.example.com/cap.png',
            'parameters': [{'name': 'key', 'value': 'k'}]}], 'userErrors': []}}}
        product_set = {'data': {'productSet': {'product': {
            'id': 'gid://shopify/Product/60', 'handle': 'cap', 'status': 'DRAFT', 'variants': {'nodes': [
                {'id': 'gid://shopify/ProductVariant/61', 'sku': 'CAP',
                 'selectedOptions': [{'name': 'Title', 'value': 'Default Title'}],
                 'inventoryItem': {'id': 'gid://shopify/InventoryItem/61', 'tracked': False}}]}}, 'userErrors': []}}}
        publications = {'data': {'publications': {'nodes': [{'id': 'gid://shopify/Publication/1', 'name': 'Online Store'}],
                                                  'pageInfo': {'hasNextPage': False}}}}
        published = {'data': {'publishablePublish': {'userErrors': []}}}

        class Upload:
            status_code = 204

        with mock_shopify({'OmShopifyStagedUploads': staged, 'OmShopifyProductSet': product_set,
                           'OmShopifyPublications': publications, 'OmShopifyPublish': published}) as fake, \
                patch('odoo.addons.om_shopify.models.om_shopify_store.request_with_retry', return_value=Upload()):
            binding = self.env['om.shopify.product.template']._shopify_export_product(self.store, template)
        self.assertEqual(fake.names(), ['OmShopifyStagedUploads', 'OmShopifyProductSet', 'OmShopifyPublications',
                                        'OmShopifyPublish'])
        self.assertEqual(fake.calls[1][1]['input']['files'][0]['originalSource'], 'https://uploads.example.com/cap.png')
        self.assertTrue(binding.image_checksum)
        with mock_shopify({'OmShopifyProductSet': product_set, 'OmShopifyPublications': publications,
                           'OmShopifyPublish': published}) as fake:
            self.env['om.shopify.product.template']._shopify_export_product(self.store, template)
        self.assertNotIn('files', fake.calls[0][1]['input'], "the same image is not sent again")

    def test_prices_stock_rules_and_stock_import(self):
        pricelist = self.env['product.pricelist'].create({'name': 'Shopify', 'item_ids': [
            (0, 0, {'compute_price': 'discount', 'price_discount': 10, 'applied_on': '3_global'})]})
        self.store.price_pricelist_id = pricelist
        with mock_shopify({'OmShopifyProduct': product(1, 'Mug', [variant(11, 'MUG-9', price='20.00')])}):
            binding = self.env['om.shopify.product.template']._shopify_import_product(self.store,
                                                                                      'gid://shopify/Product/1')
        mug = binding.variant_ids.product_id
        mug.lst_price = 20
        job = self.store._connector_enqueue('_connector_job_shopify_export_prices')
        answer = {'data': {'productVariantsBulkUpdate': {'productVariants': [], 'userErrors': []}}}
        with mock_shopify({'OmShopifyVariantsBulkUpdate': answer}) as fake:
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(fake.calls[0][1]['variants'][0]['price'], '18.00')
        # stock rules
        variant_binding = binding.variant_ids
        variant_binding.write({'stock_rule': 'percent', 'stock_value': 50})
        self.assertEqual(variant_binding._shopify_stock_quantity(9), 4)
        variant_binding.write({'stock_rule': 'buffer', 'stock_value': 2})
        self.assertEqual(variant_binding._shopify_stock_quantity(1), 0)
        variant_binding.write({'stock_rule': 'fixed', 'stock_value': 100})
        self.assertEqual(variant_binding._shopify_stock_quantity(3), 100)
        # stock import
        self.env['om.shopify.location'].create({'store_id': self.store.id, 'name': 'Shop', 'shopify_gid': 'gid://shopify/Location/1',
                                                'shopify_active': True, 'warehouse_id': self.store.warehouse_id.id})
        self.store.stock_import_apply = True
        levels = {'data': {'location': {'inventoryLevels': {'nodes': [
            {'item': {'id': 'gid://shopify/InventoryItem/11'}, 'quantities': [{'name': 'available', 'quantity': 6}]}],
            'pageInfo': {'hasNextPage': False}}}}}
        job = self.store._connector_enqueue('_connector_job_shopify_import_stock')
        with mock_shopify({'OmShopifyInventoryLevels': levels}):
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(job.result, '1 quantity(ies) imported')
        self.assertEqual(mug.with_context(warehouse_id=self.store.warehouse_id.id).qty_available, 6)

    def test_customer_import_and_mapping_and_import_by_number(self):
        customer = {'data': {'customer': {
            'id': 'gid://shopify/Customer/70', 'firstName': 'Ann', 'lastName': 'Lee', 'note': None, 'tags': ['VIP'],
            'defaultEmailAddress': {'emailAddress': 'ann@example.com'}, 'defaultPhoneNumber': None,
            'defaultAddress': {'firstName': 'Ann', 'lastName': 'Lee', 'name': 'Ann Lee', 'company': None,
                               'address1': '2 High St', 'address2': None, 'city': 'Leeds', 'zip': 'LS1',
                               'provinceCode': None, 'countryCodeV2': 'GB', 'phone': None}}}}
        with mock_shopify({'OmShopifyCustomer': customer}):
            partner = self.env['om.shopify.customer']._shopify_import_customer(self.store, 'gid://shopify/Customer/70')
        self.assertEqual((partner.name, partner.city, partner.country_id.code), ('Ann Lee', 'Leeds', 'GB'))
        self.assertEqual(partner.category_id.name, 'VIP')
        # mapping from a file
        cup = self.env['product.product'].create({'name': 'Cup', 'default_code': 'ODOO-CUP'})
        content = BinaryBytes(b'shopify_variant_id,odoo_reference,odoo_barcode\n777,ODOO-CUP,\n')
        wizard = self.env['om.shopify.mapping.wizard'].create({'store_id': self.store.id, 'file': content,
                                                               'filename': 'map.csv'})
        answer = {'data': {'productVariant': {'id': 'gid://shopify/ProductVariant/777', 'title': 'Default Title',
                                              'sku': 'SHOP-CUP', 'barcode': None,
                                              'product': {'id': 'gid://shopify/Product/77', 'title': 'Cup',
                                                          'handle': 'cup', 'status': 'ACTIVE'},
                                              'inventoryItem': {'id': 'gid://shopify/InventoryItem/777', 'tracked': True}}}}
        with mock_shopify({'OmShopifyVariant': answer}):
            wizard.action_map()
        binding = self.env['om.shopify.product']._connector_find(self.store, 'gid://shopify/ProductVariant/777')
        self.assertEqual(binding.product_id, cup)
        # import by number
        wizard = self.env['om.shopify.import.wizard'].create({'store_id': self.store.id, 'kind': 'order',
                                                              'references': '1001'})
        search = {'data': {'orders': {'nodes': [{'id': 'gid://shopify/Order/1001', 'name': '#1001', 'updatedAt': 'x'}]}}}
        with mock_shopify({'OmShopifyOrderSearch': search,
                           'OmShopifyOrder': order(lines=[line(1, 777, 77, 1, 5)], total=5)}):
            wizard.action_import()
        sale = self.env['sale.order'].search([('shopify_order_gid', '=', 'gid://shopify/Order/1001')])
        self.assertEqual(sale.order_line.product_id, cup)

    def test_payouts_and_failure_activity(self):
        journal = self.env['account.journal'].create({'name': 'Shopify Payouts', 'type': 'bank', 'code': 'SHPO'})
        self.store.write({'payout_journal_id': journal.id, 'payout_import': True})
        payouts = {'data': {'shopifyPaymentsAccount': {'payouts': {'nodes': [{
            'id': 'gid://shopify/ShopifyPaymentsPayout/5', 'issuedAt': '2026-11-15T00:00:00Z', 'status': 'PAID',
            'net': {'amount': '17.10', 'currencyCode': 'USD'}}], 'pageInfo': {'hasNextPage': False}}}}}
        transactions = {'data': {'shopifyPaymentsAccount': {'balanceTransactions': {'nodes': [
            {'id': 'b1', 'type': 'CHARGE', 'test': True, 'transactionDate': '2026-11-14T10:00:00Z',
             'amount': {'amount': '20.00', 'currencyCode': 'USD'}, 'fee': {'amount': '0.90'}, 'net': {'amount': '19.10'},
             'associatedOrder': {'id': 'gid://shopify/Order/1', 'name': '#1001'}},
            {'id': 'b2', 'type': 'REFUND', 'test': True, 'transactionDate': '2026-11-14T12:00:00Z',
             'amount': {'amount': '-2.00', 'currencyCode': 'USD'}, 'fee': {'amount': '0.00'}, 'net': {'amount': '-2.00'},
             'associatedOrder': None},
        ], 'pageInfo': {'hasNextPage': False}}}}}
        job = self.store._connector_enqueue('_connector_job_shopify_import_payouts')
        with mock_shopify({'OmShopifyPayouts': payouts, 'OmShopifyBalanceTransactions': transactions}) as fake:
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(fake.calls[1][1]['query'], 'payout_id:5')
        payout = self.store.payout_ids
        self.assertEqual(sorted(payout.statement_line_ids.mapped('amount')), [-2.0, -0.9, 20.0])
        # failure activity
        failing = self.store._connector_enqueue('_connector_job_shopify_import_payouts', max_attempts=1)
        self.store.payout_journal_id = False
        failing._run()
        self.assertEqual(failing.state, 'failed')
        self.assertTrue(self.store.activity_ids.filtered(lambda a: a.summary == 'Shopify jobs failed'))


@tagged('post_install', '-at_install')
class TestPayoutEntries(ShopifyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.state = 'connected'
        cls.mug = cls.env['product.product'].create({
            'name': 'Mug', 'default_code': 'MUG-P', 'invoice_policy': 'order', 'taxes_id': False})
        template = cls.env['om.shopify.product.template'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/Product/1', 'product_tmpl_id': cls.mug.product_tmpl_id.id})
        cls.env['om.shopify.product'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/ProductVariant/11', 'product_id': cls.mug.id,
            'template_binding_id': template.id})
        cls.bank = cls.env['account.journal'].create({'name': 'Real Bank', 'type': 'bank', 'code': 'RBNK'})

    def _payouts(self, status='PAID'):
        return {'data': {'shopifyPaymentsAccount': {'payouts': {'nodes': [{
            'id': 'gid://shopify/ShopifyPaymentsPayout/9', 'issuedAt': '2026-11-15T00:00:00Z', 'status': status,
            'net': {'amount': '19.10', 'currencyCode': self.env.company.currency_id.name}}],
            'pageInfo': {'hasNextPage': False}}}}}

    def test_transit_account_payout(self):
        self.assertEqual(self.store.payout_mode, 'statement', "the transit account is opt-in")
        self.store.write({'payout_import': True, 'payout_journal_id': self.bank.id})
        self.store.action_shopify_setup_payouts()
        self.assertEqual(self.store.payout_mode, 'entry')
        transit = self.store.payout_transit_account_id
        self.assertTrue(transit.reconcile)
        with mock_shopify({'OmShopifyOrder': order(lines=[line(1, 11, 1, 2, 10)], total=20, gateway='shopify_payments')}):
            sale = self.env['sale.order']._shopify_sync_order(self.store, 'gid://shopify/Order/1001')
        payment_line = self.env['account.move.line'].search([('account_id', '=', transit.id),
                                                             ('partner_id', 'child_of', sale.partner_id.id)])
        self.assertEqual(payment_line.debit, 20, "the payment of Shopify Payments waits on the transit account")
        st_line = self.env['account.bank.statement.line'].create({
            'journal_id': self.bank.id, 'date': '2026-11-16', 'amount': 19.10, 'payment_ref': 'SHOPIFY PAYOUT'})
        transactions = {'data': {'shopifyPaymentsAccount': {'balanceTransactions': {'nodes': [
            {'id': 'b1', 'type': 'CHARGE', 'test': False, 'transactionDate': '2026-11-14T10:00:00Z',
             'amount': {'amount': '20.00', 'currencyCode': 'USD'}, 'fee': {'amount': '0.90'}, 'net': {'amount': '19.10'},
             'associatedOrder': {'id': 'gid://shopify/Order/1001', 'name': '#1001'}}],
            'pageInfo': {'hasNextPage': False}}}}}
        no_payouts = {'data': {'shopifyPaymentsAccount': {'payouts': {'nodes': [], 'pageInfo': {'hasNextPage': False}}}}}
        job = self.store._connector_enqueue('_connector_job_shopify_import_payouts')
        with mock_shopify({'OmShopifyPayouts': [self._payouts(), no_payouts],
                           'OmShopifyBalanceTransactions': transactions}):
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        payout = self.store.payout_ids
        self.assertEqual(payout.move_id.state, 'posted')
        self.assertEqual((payout.matched_count, payout.unmatched_count), (1, 0))
        self.assertEqual(payout.fee_amount, 0.9)
        self.assertTrue(payment_line.reconciled, "the payout clears the payment of the order")
        self.assertEqual(payout.bank_line_id, st_line)
        self.assertTrue(st_line.is_reconciled, "and the bank transaction clears the payout")
        fees = payout.move_id.line_ids.filtered(lambda l: l.account_id == self.store.payout_fee_account_id)
        self.assertEqual(fees.debit, 0.9)
        # the payout fails later: its entry is reversed
        job = self.store._connector_enqueue('_connector_job_shopify_import_payouts', {'again': 1})
        with mock_shopify({'OmShopifyPayouts': [no_payouts, self._payouts('FAILED')]}):
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(payout.state, 'failed')
        reversal = payout.move_id.reversal_move_ids
        self.assertEqual(reversal.state, 'posted')
        self.assertEqual(reversal.amount_total, payout.move_id.amount_total)
