from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import WooCase, mock_woo, simple_product


def variable_product(product_id=20):
    return {
        'id': product_id, 'name': 'T-Shirt', 'slug': 't-shirt', 'type': 'variable', 'status': 'publish', 'sku': 'TS',
        'global_unique_id': '', 'price': '15.00', 'regular_price': '', 'weight': '', 'manage_stock': False,
        'images': [], 'parent_id': 0,
        'attributes': [
            {'id': 1, 'name': 'Size', 'variation': True, 'options': ['S', 'M', 'L']},
            {'id': 2, 'name': 'Color', 'variation': True, 'options': ['Red', 'Blue']},
            {'id': 0, 'name': 'Material', 'variation': False, 'options': ['Cotton']},
        ],
        'variations': [21, 22],
    }


def variation(variation_id, sku, size, color, price='15.00'):
    return {'id': variation_id, 'sku': sku, 'global_unique_id': '', 'price': price, 'regular_price': price,
            'weight': '200', 'manage_stock': True, 'stock_quantity': 3, 'image': None,
            'attributes': [{'id': 1, 'name': 'Size', 'option': size}, {'id': 2, 'name': 'Color', 'option': color}]}


@tagged('post_install', '-at_install')
class TestProductImport(WooCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.write({'state': 'connected', 'weight_unit': 'g', 'product_import_images': False})
        cls.Template = cls.env['om.woocommerce.product.template']

    def _import(self, routes, woo_id):
        with mock_woo(routes):
            return self.Template._woo_import_product(self.store, woo_id)

    def test_create_simple_product(self):
        binding = self._import({'GET products/10': simple_product(10, 'Tote Bag', 'TOTE', price='25.00')}, 10)
        template = binding.product_tmpl_id
        self.assertEqual(template.name, 'Tote Bag')
        self.assertEqual(template.default_code, 'TOTE')
        self.assertEqual(template.list_price, 25.0)
        self.assertTrue(template.is_storable)
        self.assertAlmostEqual(template.product_variant_ids.weight, 0.5, msg="500 g in kg")
        self.assertEqual(binding.variant_ids.external_id, '10')
        self.assertFalse(binding.variant_ids.parent_woo_id)

    def test_match_existing_by_sku_or_gtin(self):
        mug = self.env['product.product'].create({'name': 'Mug', 'default_code': 'MUG-1'})
        binding = self._import({'GET products/11': simple_product(11, 'Big Mug', 'MUG-1')}, 11)
        self.assertEqual(binding.variant_ids.product_id, mug)
        cup = self.env['product.product'].create({'name': 'Cup', 'barcode': '4006381333931'})
        binding = self._import({'GET products/12': simple_product(12, 'Cup', '', global_unique_id='4006381333931')}, 12)
        self.assertEqual(binding.variant_ids.product_id, cup)

    def test_no_auto_create(self):
        self.store.product_auto_create = False
        with self.assertRaises(UserError):
            self._import({'GET products/13': simple_product(13, 'Unknown', 'NOPE')}, 13)

    def test_variable_product_with_variations(self):
        # a demo-like attribute that creates no variant is not reused
        self.env['product.attribute'].create({'name': 'Size', 'create_variant': 'no_variant'})
        routes = {
            'GET products/20': variable_product(),
            'GET products/20/variations': [variation(21, 'TS-S-RED', 'S', 'Red'),
                                           variation(22, 'TS-M-BLUE', 'M', 'Blue')],
        }
        binding = self._import(routes, 20)
        template = binding.product_tmpl_id
        self.assertEqual(sorted(template.product_variant_ids.mapped('default_code')), ['TS-M-BLUE', 'TS-S-RED'],
                         "only the variations of WooCommerce exist in Odoo")
        red = binding.variant_ids.filtered(lambda v: v.sku == 'TS-S-RED')
        self.assertEqual(red.parent_woo_id, '20')
        self.assertEqual(sorted(red.product_id.product_template_attribute_value_ids.mapped('name')), ['Red', 'S'])
        self.assertNotIn('Material', template.attribute_line_ids.attribute_id.mapped('name'))
        # a new variation is added to the same template; a removed one is archived
        routes['GET products/20/variations'] = [variation(22, 'TS-M-BLUE', 'M', 'Blue'),
                                                variation(23, 'TS-L-RED', 'L', 'Red')]
        binding = self._import(routes, 20)
        self.assertEqual(binding.product_tmpl_id, template)
        self.assertIn('TS-L-RED', template.product_variant_ids.mapped('default_code'))
        self.assertFalse(binding.with_context(active_test=False).variant_ids.filtered(
            lambda v: v.external_id == '21').active)

    def test_skipped_and_trashed(self):
        result = self._import({'GET products/30': simple_product(30, 'Bundle', 'B', type='grouped')}, 30)
        self.assertIsInstance(result, str)
        binding = self._import({'GET products/31': simple_product(31, 'Old', 'OLD-1')}, 31)
        self._import({'GET products/31': simple_product(31, 'Old', 'OLD-1', status='trash')}, 31)
        self.assertFalse(binding.active)
        self.assertEqual(binding.woo_status, 'trash')

    def test_webhook_of_a_variation_imports_its_product(self):
        routes = {
            'GET products/20': variable_product(),
            'GET products/20/variations': [variation(21, 'TS-S-RED', 'S', 'Red')],
        }
        job = self.store._connector_enqueue('_connector_job_woo_product_webhook', {'id': 21, 'parent_id': 20},
                                            model_name='om.woocommerce.product.template')
        with mock_woo(routes):
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        self.assertTrue(self.Template._connector_find(self.store, 20))
