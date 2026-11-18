from odoo.tests import tagged

from .common import item, mock_woo, order, simple_product
from .test_order import WooOrderCase


@tagged('post_install', '-at_install')
class TestStockAndCompletion(WooOrderCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shirt = cls.env['product.product'].create({'name': 'Shirt', 'default_code': 'TS-S', 'is_storable': True})
        template = cls.env['om.woocommerce.product.template'].create({
            'store_id': cls.store.id, 'external_id': '20', 'product_tmpl_id': cls.shirt.product_tmpl_id.id,
            'name': 'Shirt', 'woo_type': 'variable'})
        cls.shirt_binding = cls.env['om.woocommerce.product'].create({
            'store_id': cls.store.id, 'external_id': '21', 'parent_woo_id': '20', 'product_id': cls.shirt.id,
            'template_binding_id': template.id})
        stock = cls.store.warehouse_id.lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.mug, stock, 5)
        cls.env['stock.quant']._update_available_quantity(cls.shirt, stock, 30)

    def test_export_stock(self):
        self.shirt_binding.write({'stock_rule': 'max', 'stock_value': 12})
        job = self.store._connector_enqueue('_connector_job_woo_export_stock', {'full': True})
        answer = lambda params, body: {'update': body['update']}  # noqa: E731
        with mock_woo({'POST products/batch': answer, 'POST products/20/variations/batch': answer}) as fake:
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(fake.bodies('POST products/batch')[0]['update'],
                         [{'id': 10, 'manage_stock': True, 'stock_quantity': 5}])
        self.assertEqual(fake.bodies('POST products/20/variations/batch')[0]['update'],
                         [{'id': 21, 'manage_stock': True, 'stock_quantity': 12}], "at most 12")

    def test_import_stock(self):
        self.store.stock_import_apply = True
        job = self.store._connector_enqueue('_connector_job_woo_import_stock')
        products = [dict(simple_product(10, 'Mug', 'MUG-1'), stock_quantity=8),
                    {'id': 20, 'type': 'variable', 'manage_stock': False, 'stock_quantity': None}]
        with mock_woo({'GET products': products,
                       'GET products/20/variations': [{'id': 21, 'manage_stock': True, 'stock_quantity': 4}]}):
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(self.mug.qty_available, 8)
        self.assertEqual(self.shirt.qty_available, 4)

    def _deliver(self, sale, tracking='1Z999'):
        picking = sale.picking_ids
        picking.carrier_tracking_ref = tracking
        picking.move_ids.quantity = picking.move_ids.product_uom_qty
        picking.move_ids.picked = True
        picking.button_validate()
        return self.env['om.connector.job'].search([('method_name', '=', '_connector_job_woo_complete')])

    def test_completed_with_tracking_note(self):
        sale = self._sync(order(items=[item(1, 10, 1, 10)], total=10))
        job = self._deliver(sale)
        self.assertEqual(len(job), 1)
        with mock_woo({'POST orders/1001/notes': {'id': 5},
                       'PUT orders/1001': lambda params, body: {'id': 1001, **body}}) as fake:
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        note = fake.bodies('POST orders/1001/notes')[0]
        self.assertIn('1Z999', note['note'])
        self.assertTrue(note['customer_note'])
        self.assertEqual(fake.paths()[-1], 'PUT orders/1001', "completed after the tracking number")
        self.assertEqual(sale.woo_status, 'completed')

    def test_tracking_extension_missing(self):
        self.store.fulfillment_tracking = 'plugin'
        sale = self._sync(order(items=[item(1, 10, 1, 10)], total=10))
        job = self._deliver(sale)
        with mock_woo({
            'POST wc-shipment-tracking/v3/orders/1001/shipment-trackings': (404, {'code': 'rest_no_route_x'}),
            'POST orders/1001/notes': {'id': 5},
            'PUT orders/1001': {'id': 1001, 'status': 'completed'},
        }) as fake:
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        self.assertIn('POST orders/1001/notes', fake.paths(), "the tracking number goes in a note")
