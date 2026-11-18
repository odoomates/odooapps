import base64

from odoo.tests import tagged
from odoo.tools.binary import BinaryBytes

from .common import WooCase, item, mock_woo, order
from .test_order import WooOrderCase

# a 1x1 PNG
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


def created(product_id, **extra):
    return lambda params, body: {'id': product_id, 'status': body.get('status', 'draft'), 'slug': 'p', **extra}


def batch_answer(first_id):
    """ The answer of a variations batch: the items with their ids, new ones numbered from ``first_id``. """
    def answer(params, body):
        result = {}
        for key, items in body.items():
            result[key] = [dict(i, id=i.get('id') or first_id + n) if isinstance(i, dict) else {'id': i}
                           for n, i in enumerate(items)]
        return result
    return answer


@tagged('post_install', '-at_install')
class TestProductExport(WooCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.write({'state': 'connected', 'weight_unit': 'g', 'product_export_status': 'publish'})
        cls.Template = cls.env['om.woocommerce.product.template']
        root = cls.env['product.category'].create({'name': 'Root'})
        cls.category = cls.env['product.category'].create({'name': 'Mugs', 'parent_id': cls.env[
            'product.category'].create({'name': 'Kitchen', 'parent_id': root.id}).id})

    def _export(self, routes, template, images=True):
        with mock_woo(routes) as fake:
            binding = self.Template._woo_export_product(self.store, template, images=images)
        self.fake = fake
        return binding

    def test_export_simple_product(self):
        template = self.env['product.template'].create({
            'name': 'Mug', 'default_code': 'MUG-9', 'list_price': 12.5, 'weight': 0.35, 'is_storable': True,
            'categ_id': self.category.id, 'description_sale': 'Big\nmug'})
        self.env['stock.quant']._update_available_quantity(template.product_variant_id,
                                                           self.store.warehouse_id.lot_stock_id, 4)
        routes = {
            'GET products': [],
            'GET products/categories': [],
            'POST products/categories': lambda params, body: {'id': 70 if body['name'] == 'Kitchen' else 71,
                                                              **body},
            'POST products': created(50),
        }
        binding = self._export(routes, template)
        body = self.fake.bodies('POST products')[0]
        self.assertEqual(body['type'], 'simple')
        self.assertEqual(body['status'], 'publish')
        self.assertEqual(body['sku'], 'MUG-9')
        self.assertEqual((body['regular_price'], body['sale_price']), ('12.50', ''))
        self.assertEqual(body['weight'], '350', "0.35 kg in g")
        self.assertEqual((body['manage_stock'], body['stock_quantity']), (True, 4))
        self.assertEqual(body['description'], 'Big<br/>mug')
        self.assertEqual(body['categories'], [{'id': 71}], "Kitchen > Mugs, the top category left out")
        self.assertEqual(self.fake.bodies('POST products/categories')[1], {'name': 'Mugs', 'parent': 70})
        self.assertEqual(binding.external_id, '50')
        self.assertEqual(binding.variant_ids.external_id, '50')
        self.assertEqual(binding.variant_ids.product_id, template.product_variant_id)
        # a second export updates the same product, and keeps its status
        routes['PUT products/50'] = lambda params, body: {'id': 50, 'status': 'publish', 'slug': 'mug'}
        routes['GET products/categories'] = [{'id': 70, 'name': 'Kitchen', 'parent': 0}]
        template.list_price = 15.0
        self.assertEqual(self._export(routes, template), binding)
        body = self.fake.bodies('PUT products/50')[0]
        self.assertEqual(body['regular_price'], '15.00')
        self.assertNotIn('status', body)

    def test_export_links_existing_sku(self):
        template = self.env['product.template'].create({'name': 'Cap', 'default_code': 'CAP-1'})
        routes = {
            'GET products': [{'id': 60}],
            'PUT products/60': lambda params, body: {'id': 60, 'status': 'draft'},
        }
        binding = self._export(routes, template)
        self.assertEqual(binding.external_id, '60')
        self.assertNotIn('POST products', self.fake.paths())

    def test_export_variable_product(self):
        size = self.env['product.attribute'].create({'name': 'Size', 'create_variant': 'always', 'value_ids': [
            (0, 0, {'name': 'S'}), (0, 0, {'name': 'M'})]})
        material = self.env['product.attribute'].create({'name': 'Material', 'create_variant': 'no_variant',
                                                         'value_ids': [(0, 0, {'name': 'Cotton'})]})
        template = self.env['product.template'].create({
            'name': 'Shirt', 'list_price': 20.0,
            'attribute_line_ids': [(0, 0, {'attribute_id': size.id, 'value_ids': [(6, 0, size.value_ids.ids)]}),
                                   (0, 0, {'attribute_id': material.id,
                                           'value_ids': [(6, 0, material.value_ids.ids)]})]})
        small = template.product_variant_ids.filtered(lambda p: p.product_template_attribute_value_ids.name == 'S')
        medium = template.product_variant_ids - small
        small.default_code, medium.default_code = 'SH-S', 'SH-M'
        routes = {
            'POST products': created(80),
            'GET products/80/variations': [],
            'POST products/80/variations/batch': batch_answer(81),
        }
        binding = self._export(routes, template)
        body = self.fake.bodies('POST products')[0]
        self.assertEqual(body['type'], 'variable')
        self.assertNotIn('categories', body, "the top category alone is not sent")
        self.assertEqual([(a['name'], a['variation'], a['options']) for a in body['attributes']],
                         [('Size', True, ['S', 'M']), ('Material', False, ['Cotton'])])
        created_items = self.fake.bodies('POST products/80/variations/batch')[0]['create']
        self.assertEqual(sorted(i['sku'] for i in created_items), ['SH-M', 'SH-S'])
        self.assertEqual(sorted(binding.variant_ids.mapped('parent_woo_id')), ['80', '80'])
        small_binding = binding.variant_ids.filtered(lambda v: v.product_id == small)
        # second export: the known variation is updated, a variation only in WooCommerce is removed
        routes.update({
            'PUT products/80': lambda params, body: {'id': 80, 'status': 'draft'},
            'GET products/80/variations': [
                {'id': int(small_binding.external_id), 'attributes': [{'name': 'Size', 'option': 'S'}]},
                {'id': int(binding.variant_ids.filtered(lambda v: v.product_id == medium).external_id),
                 'attributes': [{'name': 'Size', 'option': 'M'}]},
                {'id': 99, 'attributes': [{'name': 'Size', 'option': 'XL'}]}],
        })
        self._export(routes, template)
        batches = self.fake.bodies('POST products/80/variations/batch')
        self.assertEqual(len(batches[0]['update']), 2)
        self.assertEqual(batches[1], {'delete': [99]})

    def test_images_with_application_password(self):
        self.store.write({'wp_username': 'shop', 'wp_app_password': 'abcd efgh ijkl mnop'})
        template = self.env['product.template'].create({'name': 'Poster', 'image_1920': BinaryBytes(PNG)})
        routes = {
            'POST wp/v2/media': {'id': 501, 'source_url': 'https://shop.example.com/poster.png'},
            'POST products': created(90),
        }
        binding = self._export(routes, template)
        self.assertEqual(self.fake.bodies('POST products')[0]['images'], [{'id': 501}])
        self.assertTrue(binding.image_checksum)
        upload = [c for c in self.fake.calls if c[1] == 'wp/v2/media'][0]
        self.assertEqual(upload[0], 'POST')
        # the same image is not uploaded again
        routes['PUT products/90'] = lambda params, body: {'id': 90, 'status': 'draft'}
        self._export(routes, template)
        self.assertEqual(self.fake.paths(), ['PUT products/90'])
        self.assertNotIn('images', self.fake.bodies('PUT products/90')[0])

    def test_meta_data_both_ways(self):
        field = self.env['ir.model.fields']._get('product.template', 'description_sale')
        self.env['om.woocommerce.meta'].create({'store_id': self.store.id, 'resource': 'product', 'key': '_brand',
                                                'field_id': field.id, 'direction': 'both'})
        template = self.env['product.template'].create({'name': 'Lamp', 'description_sale': 'Acme'})
        binding = self._export({'POST products': created(95)}, template)
        self.assertIn({'key': '_brand', 'value': 'Acme'}, self.fake.bodies('POST products')[0]['meta_data'])
        self.store.product_import_images = False
        with mock_woo({'GET products/95': {
                'id': 95, 'name': 'Lamp', 'type': 'simple', 'status': 'draft', 'sku': '', 'global_unique_id': '',
                'price': '0', 'regular_price': '0', 'manage_stock': False, 'images': [], 'attributes': [],
                'meta_data': [{'id': 1, 'key': '_brand', 'value': 'Globex'}]}}):
            self.Template._woo_import_product(self.store, 95)
        self.assertEqual(binding.product_tmpl_id.description_sale, 'Globex')

    def test_export_prices(self):
        pricelist = self.env['product.pricelist'].create({'name': 'Shop', 'item_ids': [(0, 0, {
            'compute_price': 'discount', 'price_discount': 10, 'applied_on': '3_global'})]})
        self.store.write({'price_pricelist_id': pricelist.id})
        product = self.env['product.product'].create({'name': 'Pen', 'list_price': 10.0})
        self.assertEqual(self.store._woo_prices(product), {'regular_price': '9.00', 'sale_price': ''})
        self.store.compare_pricelist_id = self.env['product.pricelist'].create({'name': 'List'})
        self.assertEqual(self.store._woo_prices(product), {'regular_price': '10.00', 'sale_price': '9.00'})
        template = self.Template.create({'store_id': self.store.id, 'external_id': '40', 'name': 'Pen',
                                         'product_tmpl_id': product.product_tmpl_id.id})
        self.env['om.woocommerce.product'].create({'store_id': self.store.id, 'external_id': '40',
                                                   'product_id': product.id, 'template_binding_id': template.id})
        job = self.store._connector_enqueue('_connector_job_woo_export_prices')
        with mock_woo({'POST products/batch': lambda params, body: {'update': body['update']}}) as fake:
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        self.assertEqual(fake.bodies('POST products/batch')[0]['update'],
                         [{'id': 40, 'regular_price': '10.00', 'sale_price': '9.00'}])
        self.assertTrue(self.store.price_last_sync)

    def test_publish(self):
        product = self.env['product.product'].create({'name': 'Pin'})
        binding = self.Template.create({'store_id': self.store.id, 'external_id': '41', 'name': 'Pin',
                                        'product_tmpl_id': product.product_tmpl_id.id, 'woo_status': 'draft'})
        with mock_woo({'PUT products/41': lambda params, body: {'id': 41, 'status': body['status']}}):
            binding.action_woo_publish()
        self.assertEqual(binding.woo_status, 'publish')


@tagged('post_install', '-at_install')
class TestShippingCarrier(WooOrderCase):

    def test_shipping_method_carrier(self):
        shipping = [{'id': 2, 'method_title': 'Express', 'method_id': 'flat_rate', 'total': '5.00', 'total_tax': '0',
                     'taxes': []}]
        sale = self._sync(order(order_id=2001, items=[item(1, 10, 1, 10)], shipping=shipping, total=15))
        method = self.env['om.woocommerce.shipping'].search([('store_id', '=', self.store.id)])
        self.assertEqual((method.name, method.title), ('flat_rate', 'Express'))
        self.assertFalse(sale.carrier_id)
        carrier_product = self.env['product.product'].create({'name': 'Express', 'type': 'service'})
        method.carrier_id = self.env['delivery.carrier'].create({'name': 'Express', 'product_id': carrier_product.id})
        sale = self._sync(order(order_id=2002, items=[item(1, 10, 1, 10)], shipping=shipping, total=15))
        self.assertEqual(sale.carrier_id, method.carrier_id)
        self.assertEqual(sale.order_line.filtered('is_delivery').product_id, carrier_product)
        self.assertEqual(self.env['om.woocommerce.shipping'].search_count([('store_id', '=', self.store.id)]), 1)
