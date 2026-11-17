from odoo.tests import tagged

from .common import ShopifyCase, line, mock_shopify, order


@tagged('post_install', '-at_install')
class TestStockAndFulfillment(ShopifyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.write({'state': 'connected'})
        cls.warehouse = cls.store.warehouse_id
        cls.location = cls.env['om.shopify.location'].create({
            'store_id': cls.store.id, 'name': 'Shop', 'shopify_gid': 'gid://shopify/Location/1',
            'shopify_active': True, 'warehouse_id': cls.warehouse.id})
        cls.mug = cls.env['product.product'].create({
            'name': 'Mug', 'default_code': 'MUG-1', 'is_storable': True, 'invoice_policy': 'order', 'taxes_id': False})
        template = cls.env['om.shopify.product.template'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/Product/1', 'product_tmpl_id': cls.mug.product_tmpl_id.id})
        cls.env['om.shopify.product'].create({
            'store_id': cls.store.id, 'external_id': 'gid://shopify/ProductVariant/11', 'product_id': cls.mug.id,
            'template_binding_id': template.id, 'inventory_item_gid': 'gid://shopify/InventoryItem/11', 'tracked': True})
        cls.env['stock.quant']._update_available_quantity(cls.mug, cls.warehouse.lot_stock_id, 7)

    def test_export_stock(self):
        job = self.store._connector_enqueue('_connector_job_shopify_export_stock', {'full': True})
        answer = {'data': {'inventorySetQuantities': {'inventoryAdjustmentGroup': {'id': 'g'}, 'userErrors': []}}}
        with mock_shopify({'OmShopifyInventorySet': answer}) as fake:
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        variables = fake.calls[0][1]
        self.assertEqual(variables['input']['quantities'], [{
            'inventoryItemId': 'gid://shopify/InventoryItem/11', 'locationId': 'gid://shopify/Location/1',
            'quantity': 7, 'changeFromQuantity': None}])
        self.assertTrue(variables['key'])
        self.assertTrue(self.store.stock_last_sync)

    def test_fulfillment_after_delivery(self):
        self.store.workflow_id.write({'create_invoice': False, 'register_payment': False})
        with mock_shopify({'OmShopifyOrder': order(lines=[line(1, 11, 1, 2, 10)], total=20)}):
            sale = self.env['sale.order']._shopify_sync_order(self.store, 'gid://shopify/Order/1001')
        picking = sale.picking_ids
        picking.carrier_tracking_ref = 'TRACK123'
        picking.move_ids.quantity = 2
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        job = self.env['om.connector.job'].search([('dedupe_key', '=', f'fulfill:{picking.id}')])
        self.assertTrue(job)
        fulfillment_orders = {'data': {'order': {'id': sale.shopify_order_gid, 'fulfillmentOrders': {'nodes': [{
            'id': 'gid://shopify/FulfillmentOrder/5', 'status': 'OPEN',
            'assignedLocation': {'location': {'id': 'gid://shopify/Location/1'}},
            'lineItems': {'nodes': [{'id': 'gid://shopify/FulfillmentOrderLineItem/51', 'remainingQuantity': 2,
                                     'lineItem': {'id': 'gid://shopify/LineItem/1'}}]},
        }]}}}}
        created = {'data': {'fulfillmentCreate': {'fulfillment': {'id': 'gid://shopify/Fulfillment/9',
                                                                  'status': 'SUCCESS'}, 'userErrors': []}}}
        with mock_shopify({'OmShopifyFulfillmentOrders': fulfillment_orders,
                           'OmShopifyFulfillmentCreate': created}) as fake:
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        fulfillment = fake.calls[1][1]['fulfillment']
        self.assertEqual(fulfillment['lineItemsByFulfillmentOrder'], [{
            'fulfillmentOrderId': 'gid://shopify/FulfillmentOrder/5',
            'fulfillmentOrderLineItems': [{'id': 'gid://shopify/FulfillmentOrderLineItem/51', 'quantity': 2}]}])
        self.assertEqual(fulfillment['trackingInfo']['number'], 'TRACK123')
        self.assertEqual(picking.shopify_fulfillment_gid, 'gid://shopify/Fulfillment/9')
