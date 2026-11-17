import json

from odoo.tests import tagged

from .common import ShopifyCase, line, mock_shopify, order, product, variant


@tagged('post_install', '-at_install')
class TestMetafieldsAndB2B(ShopifyCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store.state = 'connected'

    def _field(self, model, name):
        return self.env['ir.model.fields']._get(model, name)

    def test_metafields_import_and_export(self):
        Meta = self.env['om.shopify.metafield']
        Meta.create([
            {'store_id': self.store.id, 'resource': 'product', 'namespace': 'custom', 'key': 'care',
             'field_id': self._field('product.template', 'description_sale').id, 'direction': 'both',
             'metafield_type': 'multi_line_text_field'},
            {'store_id': self.store.id, 'resource': 'variant', 'namespace': 'custom', 'key': 'weight_kg',
             'field_id': self._field('product.product', 'weight').id, 'direction': 'import',
             'metafield_type': 'number_decimal'},
            {'store_id': self.store.id, 'resource': 'order', 'namespace': 'custom', 'key': 'po',
             'field_id': self._field('sale.order', 'client_order_ref').id},
        ])
        answer = product(1, 'Mug', [dict(variant(11, 'MUG-M'), metafields={'nodes': [
            {'namespace': 'custom', 'key': 'weight_kg', 'value': '0.75', 'type': 'number_decimal'}]})])
        answer['data']['product']['metafields'] = {'nodes': [
            {'namespace': 'custom', 'key': 'care', 'value': 'Hand wash', 'type': 'multi_line_text_field'},
            {'namespace': 'other', 'key': 'x', 'value': 'ignored', 'type': 'single_line_text_field'}]}
        with mock_shopify({'OmShopifyProduct': answer}) as fake:
            binding = self.env['om.shopify.product.template']._shopify_import_product(self.store, 'gid://shopify/Product/1')
        query = fake.calls and True
        self.assertTrue(query)
        self.assertEqual(binding.product_tmpl_id.description_sale, 'Hand wash')
        self.assertAlmostEqual(binding.variant_ids.product_id.weight, 0.75)
        sent = self.store._shopify_query('query { product { # om:metafields:product\n variants { # om:metafields:variant\n } } }')
        self.assertIn('metafields(first: 50, keys: ["custom.care"])', sent)
        self.assertIn('keys: ["custom.weight_kg"]', sent)
        self.assertEqual(self.store._shopify_metafield_inputs('product', binding.product_tmpl_id), [
            {'namespace': 'custom', 'key': 'care', 'type': 'multi_line_text_field', 'value': 'Hand wash'}])
        # order metafield
        mug = binding.variant_ids.product_id
        mug.write({'invoice_policy': 'order', 'taxes_id': False})
        data = order(lines=[line(1, 11, 1, 1, 10)], total=10, metafields={'nodes': [
            {'namespace': 'custom', 'key': 'po', 'value': 'PO-778', 'type': 'single_line_text_field'}]})
        with mock_shopify({'OmShopifyOrder': data}):
            sale = self.env['sale.order']._shopify_sync_order(self.store, 'gid://shopify/Order/1001')
        self.assertEqual(sale.client_order_ref, 'PO-778')

    def test_b2b_company_order_and_price_list(self):
        fiscal = self.env['account.fiscal.position'].create({'name': 'Tax exempt'})
        self.store.write({'b2b_import': True, 'b2b_tax_exempt_fiscal_position_id': fiscal.id})
        self.assertIn('COMPANIES_CREATE', self.store._shopify_webhook_handlers())
        address = {'address1': '5 Dock Road', 'address2': None, 'city': 'Seattle', 'zip': '98101', 'zoneCode': 'WA',
                   'countryCode': 'US', 'phone': None, 'companyName': 'Acme', 'recipient': 'Receiving'}
        company = {'data': {'company': {
            'id': 'gid://shopify/Company/3', 'name': 'Acme Corp', 'externalId': 'ACME', 'note': None,
            'locations': {'nodes': [{
                'id': 'gid://shopify/CompanyLocation/31', 'name': 'Acme Seattle', 'externalId': None,
                'billingAddress': address, 'shippingAddress': address, 'taxSettings': {'taxExempt': True},
                'buyerExperienceConfiguration': {'paymentTermsTemplate': {'name': 'Net 45', 'dueInDays': 45,
                                                                          'paymentTermsType': 'NET'}}}]},
            'contacts': {'nodes': []}}}}
        mug = self.env['product.product'].create({'name': 'Mug', 'default_code': 'MUG-B', 'invoice_policy': 'order',
                                                  'taxes_id': False})
        template = self.env['om.shopify.product.template'].create({
            'store_id': self.store.id, 'external_id': 'gid://shopify/Product/1', 'product_tmpl_id': mug.product_tmpl_id.id})
        self.env['om.shopify.product'].create({
            'store_id': self.store.id, 'external_id': 'gid://shopify/ProductVariant/11', 'product_id': mug.id,
            'template_binding_id': template.id})
        data = order(lines=[line(1, 11, 1, 10, 10)], total=100, purchasingEntity={
            'company': {'id': 'gid://shopify/Company/3'}, 'location': {'id': 'gid://shopify/CompanyLocation/31'},
            'contact': None})
        with mock_shopify({'OmShopifyOrder': data, 'OmShopifyCompany': company}):
            sale = self.env['sale.order']._shopify_sync_order(self.store, 'gid://shopify/Order/1001')
        acme = self.env['om.shopify.company'].search([('store_id', '=', self.store.id)]).partner_id
        self.assertEqual((acme.name, acme.ref, acme.commercial_partner_id), ('Acme Corp', 'ACME', acme))
        self.assertEqual(sale.partner_id, acme)
        self.assertEqual(sale.partner_invoice_id.parent_id, acme)
        self.assertEqual(sale.partner_invoice_id.city, 'Seattle')
        self.assertEqual(sale.payment_term_id.name, 'Net 45')
        self.assertEqual(sale.payment_term_id.line_ids.nb_days, 45)
        self.assertEqual(sale.fiscal_position_id, fiscal)
        # price list
        lists = {'data': {'priceLists': {'nodes': [{'id': 'gid://shopify/PriceList/8', 'name': 'Wholesale',
                                                    'currency': self.env.company.currency_id.name}],
                                         'pageInfo': {'hasNextPage': False}}}}
        with mock_shopify({'OmShopifyPriceLists': lists}):
            self.store.action_shopify_import_price_lists()
        wholesale = self.env['product.pricelist'].create({'name': 'Wholesale', 'item_ids': [
            (0, 0, {'compute_price': 'fixed', 'fixed_price': 7.5, 'applied_on': '0_product_variant',
                    'product_id': mug.id})]})
        self.store.price_list_ids.pricelist_id = wholesale
        job = self.store._connector_enqueue('_connector_job_shopify_export_prices')
        ok = {'data': {'productVariantsBulkUpdate': {'productVariants': [], 'userErrors': []},
                       'priceListFixedPricesAdd': {'prices': [], 'userErrors': []}}}
        with mock_shopify({'OmShopifyVariantsBulkUpdate': ok, 'OmShopifyPriceListPrices': ok}) as fake:
            job._run()
        self.assertEqual(job.state, 'done', job.error)
        call = next(c for c in fake.calls if c[0] == 'OmShopifyPriceListPrices')
        self.assertEqual(call[1]['priceListId'], 'gid://shopify/PriceList/8')
        self.assertEqual(call[1]['prices'][0]['price']['amount'], '7.50')
