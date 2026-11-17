import json

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ShopifyCase, mock_shopify, product, variant


@tagged('post_install', '-at_install')
class TestProductImport(ShopifyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.state = 'connected'
        cls.Binding = cls.env['om.shopify.product.template']

    def _import(self, answer, gid='gid://shopify/Product/1'):
        with mock_shopify({'OmShopifyProduct': answer}):
            return self.Binding._shopify_import_product(self.store, gid)

    def test_match_existing_by_sku(self):
        existing = self.env['product.product'].create({'name': 'Mug', 'default_code': 'MUG-1', 'is_storable': True})
        binding = self._import(product(1, 'Coffee Mug', [variant(11, 'MUG-1')]))
        self.assertEqual(binding.product_tmpl_id, existing.product_tmpl_id)
        self.assertEqual(binding.variant_ids.product_id, existing)
        self.assertEqual(binding.variant_ids.inventory_item_gid, 'gid://shopify/InventoryItem/11')
        self.assertEqual(existing.name, 'Mug', "an existing product is not renamed")

    def test_match_by_barcode(self):
        self.store.product_match = 'barcode'
        existing = self.env['product.product'].create({'name': 'Cap', 'barcode': '4006381333931'})
        binding = self._import(product(1, 'Cap', [variant(11, 'OTHER', barcode='4006381333931')]))
        self.assertEqual(binding.variant_ids.product_id, existing)

    def test_create_simple_product(self):
        binding = self._import(product(1, 'Tote Bag', [variant(11, 'TOTE', price='25.00')]))
        template = binding.product_tmpl_id
        self.assertEqual(template.name, 'Tote Bag')
        self.assertEqual(template.default_code, 'TOTE')
        self.assertEqual(template.list_price, 25.0)
        self.assertTrue(template.is_storable)
        self.assertAlmostEqual(template.product_variant_ids.weight, 0.5)

    def test_create_product_with_variants(self):
        options = [{'name': 'Size', 'position': 1, 'optionValues': [{'name': 'S'}, {'name': 'M'}, {'name': 'L'}]},
                   {'name': 'Color', 'position': 2, 'optionValues': [{'name': 'Red'}, {'name': 'Blue'}]}]
        variants = [
            variant(11, 'TS-S-RED', options=[{'name': 'Size', 'value': 'S'}, {'name': 'Color', 'value': 'Red'}]),
            variant(12, 'TS-M-BLUE', options=[{'name': 'Size', 'value': 'M'}, {'name': 'Color', 'value': 'Blue'}]),
        ]
        binding = self._import(product(1, 'T-Shirt', variants, options))
        template = binding.product_tmpl_id
        self.assertEqual(len(binding.variant_ids), 2)
        self.assertEqual(sorted(template.product_variant_ids.mapped('default_code')), ['TS-M-BLUE', 'TS-S-RED'],
                         "only the variants of Shopify exist in Odoo")
        red = binding.variant_ids.filtered(lambda v: v.sku == 'TS-S-RED').product_id
        self.assertEqual(sorted(red.product_template_attribute_value_ids.mapped('name')), ['Red', 'S'])
        # a new variant in Shopify is added to the same template
        variants.append(variant(13, 'TS-L-RED', options=[{'name': 'Size', 'value': 'L'},
                                                         {'name': 'Color', 'value': 'Red'}]))
        binding = self._import(product(1, 'T-Shirt', variants, options))
        self.assertEqual(len(binding.variant_ids), 3)
        self.assertEqual(len(template.product_variant_ids), 3)

    def test_no_auto_create(self):
        self.store.product_auto_create = False
        with self.assertRaises(UserError):
            self._import(product(1, 'Unknown', [variant(11, 'NOPE')]))

    def test_removed_variant_is_archived(self):
        self.env['product.product'].create({'name': 'A', 'default_code': 'A'})
        self.env['product.product'].create({'name': 'B', 'default_code': 'B'})
        self._import(product(1, 'AB', [variant(11, 'A', title='A'), variant(12, 'B', title='B')]))
        binding = self._import(product(1, 'AB', [variant(11, 'A', title='A')]))
        self.assertEqual(binding.with_context(active_test=False).variant_ids.filtered('active').mapped('sku'), ['A'])

    def test_fetch_job_queues_one_job_per_product(self):
        pages = {'data': {'products': {'nodes': [{'id': 'gid://shopify/Product/1', 'updatedAt': 'x'},
                                                 {'id': 'gid://shopify/Product/2', 'updatedAt': 'x'}],
                                       'pageInfo': {'hasNextPage': False, 'endCursor': None}}}}
        job = self.store._connector_enqueue('_connector_job_shopify_fetch_products', {'full': True})
        with mock_shopify({'OmShopifyProductIds': pages}):
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        queued = self.env['om.connector.job'].search(self.store._connector_job_domain() + [
            ('method_name', '=', '_connector_job_shopify_import_product')])
        self.assertEqual(sorted(queued.mapped('dedupe_key')),
                         ['product:gid://shopify/Product/1', 'product:gid://shopify/Product/2'])
        self.assertTrue(self.store.product_last_sync)

    def test_bulk_import(self):
        lines = [
            {'id': 'gid://shopify/Product/1', 'title': 'Bulk Mug', 'handle': 'bulk-mug', 'status': 'ACTIVE',
             'options': [{'name': 'Title', 'position': 1, 'optionValues': [{'name': 'Default Title'}]}],
             'featuredMedia': None, 'updatedAt': 'x'},
            {**variant(11, 'BULK-MUG'), '__parentId': 'gid://shopify/Product/1'},
            {'id': 'gid://shopify/Product/2', 'title': 'Bulk Cap', 'handle': 'bulk-cap', 'status': 'ACTIVE',
             'options': [{'name': 'Title', 'position': 1, 'optionValues': [{'name': 'Default Title'}]}],
             'featuredMedia': None, 'updatedAt': 'x'},
            {**variant(21, 'BULK-CAP'), '__parentId': 'gid://shopify/Product/2'},
        ]
        url = 'https://storage.example.com/bulk.jsonl'
        self.store.action_shopify_import_products()
        start = self.env['om.connector.job'].search(self.store._connector_job_domain() + [
            ('method_name', '=', '_connector_job_shopify_bulk_products')])
        run = {'data': {'bulkOperationRunQuery': {'bulkOperation': {'id': 'gid://shopify/BulkOperation/5',
                                                                    'status': 'CREATED'}, 'userErrors': []}}}
        with mock_shopify({'OmShopifyBulkRun': run}):
            start._run()
        self.assertEqual(start.state, 'done', start.error)
        poll = self.env['om.connector.job'].search([('dedupe_key', '=', 'bulk:gid://shopify/BulkOperation/5')])
        running = {'data': {'bulkOperation': {'id': 'b', 'status': 'RUNNING', 'objectCount': '2', 'url': None}}}
        done = {'data': {'bulkOperation': {'id': 'b', 'status': 'COMPLETED', 'objectCount': '4', 'url': url}}}
        with mock_shopify({'OmShopifyBulkStatus': running}):
            poll._run()
        self.assertEqual(poll.state, 'pending', "waits while Shopify prepares the file")
        with mock_shopify({'OmShopifyBulkStatus': done}, files={url: [json.dumps(l) for l in lines]}):
            poll._run()
        self.assertEqual(poll.state, 'done', poll.error)
        imports = self.env['om.connector.job'].search(self.store._connector_job_domain() + [
            ('method_name', '=', '_connector_job_shopify_import_product')])
        self.assertEqual(len(imports), 2)
        with mock_shopify({}) as fake:
            for job in imports:
                job._run()
        self.assertEqual(fake.calls, [], "the products of the file are imported without asking Shopify again")
        self.assertEqual(sorted(imports.mapped('state')), ['done', 'done'])
        self.assertEqual(sorted(self.Binding.search([('store_id', '=', self.store.id)]).mapped('name')),
                         ['Bulk Cap', 'Bulk Mug'])
