import hashlib
import logging
import math

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

from ..tools import queries

_logger = logging.getLogger(__name__)

DEFAULT_OPTION = ('Title', 'Default Title')
WEIGHT_TO_KG = {'KILOGRAMS': 1.0, 'GRAMS': 0.001, 'POUNDS': 0.45359237, 'OUNCES': 0.028349523125}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class OmShopifyProductTemplate(models.Model):
    """ A Shopify product, linked to an Odoo product template. """
    _name = 'om.shopify.product.template'
    _description = 'Shopify Product'
    _inherit = ['om.connector.binding.mixin']
    _order = 'store_id, name'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'product_tmpl_id'

    name = fields.Char(readonly=True)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product', required=True, ondelete='cascade',
                                      index=True)
    shopify_status = fields.Selection([
        ('ACTIVE', 'Active'), ('DRAFT', 'Draft'), ('ARCHIVED', 'Archived'), ('UNLISTED', 'Unlisted'),
        ('deleted', 'Deleted'),
    ], string='Status in Shopify', readonly=True)
    handle = fields.Char(readonly=True)
    variant_ids = fields.One2many('om.shopify.product', 'template_binding_id', string='Variants')
    active = fields.Boolean(default=True)
    image_checksum = fields.Char(readonly=True, copy=False, help="Checksum of the last image sent to Shopify.")

    _store_external_unique = models.Constraint('unique (store_id, external_id)',
                                               "A Shopify product is linked once per store.")

    def action_shopify_export(self):
        for binding in self:
            binding.store_id._connector_enqueue(
                '_connector_job_shopify_export_product',
                {'template_id': binding.product_tmpl_id.id, 'at': fields.Datetime.to_string(fields.Datetime.now())},
                model_name='om.shopify.product.template', name=_("Export %(product)s", product=binding.name),
                dedupe_key=f'export:{binding.product_tmpl_id.id}')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': _("Export queued."), 'type': 'info'}}

    def action_open_in_shopify(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'https://{self.store_id.shop_domain}/admin/products/{self.external_id.rsplit("/", 1)[-1]}',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @api.model
    def _connector_job_shopify_import_product(self, job):
        return self._shopify_import_product(job.backend, job.payload['id'], data=job.payload.get('data'))

    @api.model
    def _connector_job_shopify_product_webhook(self, job):
        gid = job.payload.get('admin_graphql_api_id') or f"gid://shopify/Product/{job.payload['id']}"
        return self._shopify_import_product(job.backend, gid, from_webhook=True)

    @api.model
    def _connector_job_shopify_product_deleted(self, job):
        gid = job.payload.get('admin_graphql_api_id') or f"gid://shopify/Product/{job.payload['id']}"
        bindings = self.with_context(active_test=False)._connector_find(job.backend, gid)
        bindings.write({'shopify_status': 'deleted', 'active': False})
        bindings.variant_ids.write({'active': False})
        return _("%(count)s product(s) unlinked", count=len(bindings))

    @api.model
    def _shopify_fetch_product(self, store, gid):
        """ The product ``gid`` with all its variants, or None if it does not exist anymore. """
        product, cursor = None, None
        while True:
            data = store._shopify_execute(store._shopify_query(queries.PRODUCT), {'id': gid, 'cursor': cursor}).get('product')
            if not data:
                return product
            variants = data.pop('variants')
            if product is None:
                product = dict(data, variants=[])
            product['variants'] += variants.get('nodes') or []
            if not (variants.get('pageInfo') or {}).get('hasNextPage'):
                return product
            cursor = variants['pageInfo']['endCursor']

    @api.model
    def _shopify_import_product(self, store, gid, from_webhook=False, data=None):
        """ Import or update the Shopify product ``gid`` (``data``: given by a bulk operation, else
        read from Shopify): find or create the Odoo product of each variant, and link them. Gives the
        linked template. """
        data = data or self._shopify_fetch_product(store, gid)
        if not data:
            return _("Product %(id)s does not exist anymore", id=gid)
        binding = self.with_context(active_test=False)._connector_find(store, gid)
        variant_bindings = {b.external_id: b for b in binding.with_context(active_test=False).variant_ids}
        Variant = self.env['om.shopify.product']
        products = {}
        for variant in data['variants']:
            product = variant_bindings[variant['id']].product_id if variant['id'] in variant_bindings else None
            products[variant['id']] = product or Variant._shopify_match(store, variant)
        missing = [v for v in data['variants'] if not products[v['id']]]
        if missing:
            if not store.product_auto_create:
                if from_webhook and not binding:
                    return _("No Odoo product for %(name)s: not imported", name=data['title'])
                raise UserError(_(
                    "No Odoo product has the SKU or barcode of these variants of %(name)s: %(variants)s. Create them, "
                    "or allow the store to create the products.", name=data['title'],
                    variants=', '.join(v.get('sku') or v.get('barcode') or v['title'] for v in missing)))
            template = next((p.product_tmpl_id for p in products.values() if p), None) or binding.product_tmpl_id
            products.update(self._shopify_create_products(store, data, missing, template or None))
        templates = self.env['product.template'].union(p.product_tmpl_id for p in products.values())
        template = binding.product_tmpl_id if binding.product_tmpl_id in templates else templates[:1]
        vals = {
            'name': data['title'],
            'shopify_status': data.get('status'),
            'handle': data.get('handle'),
            'active': True,
        }
        binding = self._connector_bind(store, gid, template, vals)
        store._shopify_apply_metafields('product', template, data.get('metafields'))
        for variant in data['variants']:
            Variant._shopify_bind_variant(store, binding, variant, products[variant['id']])
            store._shopify_apply_metafields('variant', products[variant['id']], variant.get('metafields'))
        stale = binding.with_context(active_test=False).variant_ids.filtered(
            lambda b: b.external_id not in {v['id'] for v in data['variants']})
        stale.write({'active': False})
        if store.product_import_images:
            self._shopify_import_images(store, template, data, products)
        return binding

    @api.model
    def _shopify_create_products(self, store, data, variants, template=None):
        """ Create the Odoo products of ``variants`` of the Shopify product ``data``; in ``template``
        when given. Gives ``{variant id: product.product}``. """
        options = [o for o in sorted(data.get('options') or [], key=lambda o: o.get('position') or 0)
                   if (o['name'], tuple(v['name'] for v in o.get('optionValues') or [])) != (DEFAULT_OPTION[0], (DEFAULT_OPTION[1],))]
        first = variants[0]
        tracked = any((v.get('inventoryItem') or {}).get('tracked') for v in data['variants'])
        new_template = template is None
        # no tracking: the attribute lines replace the variants the tracking of the template looks at
        Template = self.env['product.template'].with_context(tracking_disable=True)
        if new_template:
            template = Template.create({
                'name': data['title'],
                'type': 'consu',
                'is_storable': tracked,
                'list_price': float(first.get('price') or 0.0),
                'description_sale': False,
                'company_id': False,
                'default_code': first.get('sku') or False if not options else False,
                'barcode': self.env['om.shopify.product']._shopify_free_barcode(first.get('barcode')) if not options else False,
            })
        template = template.with_context(tracking_disable=True)
        if not options:
            product = template.product_variant_ids[:1]
            self.env['om.shopify.product']._shopify_update_variant(product, first)
            return {first['id']: product}
        variants_before = template.product_variant_ids if not new_template else self.env['product.product']
        # one attribute per option; a new attribute only makes the variants asked for
        Attribute = self.env['product.attribute']
        attribute_values = {}
        for option in options:
            attribute = Attribute.search([('name', '=ilike', option['name']), ('create_variant', '!=', 'no_variant')],
                                         limit=1) or Attribute.create(
                {'name': option['name'], 'create_variant': 'dynamic'})
            values = attribute_values.setdefault(option['name'], {'attribute': attribute, 'values': {}})
            for value_name in [v['name'] for v in option.get('optionValues') or []]:
                value = attribute.value_ids.filtered(lambda v: v.name.lower() == value_name.lower())[:1] or \
                    self.env['product.attribute.value'].create({'attribute_id': attribute.id, 'name': value_name})
                values['values'][value_name] = value
        for option_name, info in attribute_values.items():
            line = template.attribute_line_ids.filtered(lambda l: l.attribute_id == info['attribute'])
            wanted = self.env['product.attribute.value'].union(info['values'].values())
            if line:
                line.value_ids = [fields.Command.link(v.id) for v in wanted]
            else:
                template.attribute_line_ids = [fields.Command.create({
                    'attribute_id': info['attribute'].id,
                    'value_ids': [fields.Command.set(wanted.ids)],
                })]
        result = {}
        for variant in variants:
            ptavs = self.env['product.template.attribute.value']
            for selected in variant.get('selectedOptions') or []:
                info = attribute_values.get(selected['name'])
                if not info:
                    continue
                value = info['values'].get(selected['value'])
                ptavs |= template.attribute_line_ids.product_template_value_ids.filtered(
                    lambda v, value=value: v.product_attribute_value_id == value)
            product = template._create_product_variant(ptavs) if ptavs else template.product_variant_ids[:1]
            if not product:
                raise UserError(_("The variant %(variant)s of %(product)s cannot be created in Odoo.",
                                  variant=variant['title'], product=data['title']))
            self.env['om.shopify.product']._shopify_update_variant(product, variant)
            result[variant['id']] = product
        # attributes that make every combination create variants Shopify does not have: removed,
        # as long as they were just made here
        made = self.env['product.product'].union(result.values())
        bound = self.env['om.shopify.product'].with_context(active_test=False).search(
            [('product_id', 'in', template.with_context(active_test=False).product_variant_ids.ids)]).product_id
        (template.product_variant_ids - variants_before - made - bound).unlink()
        return result

    @api.model
    def _shopify_download(self, url):
        if not url:
            return None
        try:
            response = requests.get(url, timeout=15)
        except requests.RequestException as e:
            _logger.info("Image %s not downloaded: %s", url, e)
            return None
        if response.ok and response.content and len(response.content) <= MAX_IMAGE_BYTES:
            return BinaryBytes(response.content)
        return None

    @api.model
    def _shopify_import_images(self, store, template, data, products):
        """ The main image, the other images (in the eCommerce gallery when it is installed) and the
        image of each variant, for the Odoo products without one. """
        def url_of(media):
            return (((media or {}).get('preview') or {}).get('image') or {}).get('url')

        main_url = url_of(data.get('featuredMedia'))
        if not template.image_1920 and (image := self._shopify_download(main_url)):
            template.image_1920 = image
        if 'product.image' in self.env and 'product_tmpl_id' in self.env['product.image']._fields \
                and not template.product_template_image_ids:
            for media in (data.get('media') or {}).get('nodes') or []:
                url = url_of(media)
                if url and url != main_url and (image := self._shopify_download(url)):
                    self.env['product.image'].create({'product_tmpl_id': template.id, 'name': template.name,
                                                      'image_1920': image})
        if len(products) > 1:
            for variant in data['variants']:
                product = products.get(variant['id'])
                url = url_of(((variant.get('media') or {}).get('nodes') or [None])[0])
                if product and url and url != main_url and not product.image_variant_1920 \
                        and (image := self._shopify_download(url)):
                    product.image_variant_1920 = image

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def _connector_job_shopify_export_product(self, job):
        template = self.env['product.template'].browse(job.payload['template_id']).exists()
        if not template:
            return _("The product does not exist anymore")
        return self._shopify_export_product(job.backend, template, job.payload.get('images', True))

    @api.model
    def _shopify_option_lines(self, template):
        return template.attribute_line_ids.filtered(lambda l: l.attribute_id.create_variant != 'no_variant')

    @api.model
    def _shopify_variant_options(self, product, lines):
        values = product.product_template_attribute_value_ids
        return [{'optionName': line.attribute_id.name,
                 'name': values.filtered(lambda v, line=line: v.attribute_line_id == line)[:1].name}
                for line in lines]

    @api.model
    def _shopify_export_product(self, store, template, images=True):
        """ Create or update ``template`` in Shopify, with its variants, prices, weight and image.
        Odoo is the master of the products it exports: the variants of Shopify that are not in Odoo
        are removed. Gives the binding. """
        binding = self.with_context(active_test=False).search(
            [('store_id', '=', store.id), ('product_tmpl_id', '=', template.id)], limit=1)
        lines = self._shopify_option_lines(template)
        products = template.product_variant_ids
        if len(products) > 2048:
            raise UserError(_("Shopify has at most 2048 variants per product: %(product)s has %(count)s.",
                              product=template.name, count=len(products)))
        if lines:
            used = products.product_template_attribute_value_ids
            options = [{'name': line.attribute_id.name, 'position': position,
                        'values': [{'name': v.name} for v in line.product_template_value_ids if v in used]}
                       for position, line in enumerate(lines, 1)]
        else:
            options = [{'name': DEFAULT_OPTION[0], 'position': 1, 'values': [{'name': DEFAULT_OPTION[1]}]}]
        variants = []
        for product in products:
            price, compare_at = store._shopify_prices(product)
            variant = {
                'optionValues': self._shopify_variant_options(product, lines) if lines
                else [{'optionName': DEFAULT_OPTION[0], 'name': DEFAULT_OPTION[1]}],
                'price': f'{price:.2f}',
                'inventoryPolicy': 'DENY',
                'inventoryItem': {
                    'sku': product.default_code or '',
                    'tracked': bool(product.is_storable),
                    'measurement': {'weight': {'unit': 'KILOGRAMS', 'value': product.weight or 0.0}},
                },
            }
            if compare_at:
                variant['compareAtPrice'] = f'{compare_at:.2f}'
            if product.barcode:
                variant['barcode'] = product.barcode
            if metafields := store._shopify_metafield_inputs('variant', product):
                variant['metafields'] = metafields
            variants.append(variant)
        product_input = {
            'title': template.name,
            'descriptionHtml': template.description_sale and str(template.description_sale).replace('\n', '<br/>') or '',
            'vendor': template.seller_ids[:1].partner_id.name or store.shop_name or '',
            'productType': template.categ_id.name or '',
            'status': store.product_export_status,
            'productOptions': options,
            'variants': variants,
        }
        if metafields := store._shopify_metafield_inputs('product', template):
            product_input['metafields'] = metafields
        if images and template.image_1920:
            checksum = hashlib.sha1(bytes(template.image_1920)).hexdigest()
            if not binding or binding.image_checksum != checksum:
                product_input['files'] = [{'originalSource': store._shopify_upload_image(template),
                                           'alt': template.name, 'contentType': 'IMAGE'}]
        else:
            checksum = binding.image_checksum if binding else False
        variables = {'input': product_input}
        if binding:
            variables['identifier'] = {'id': binding.external_id}
        result = store._shopify_mutate(queries.PRODUCT_SET, variables, 'productSet')
        data = result.get('product') or {}
        vals = {'name': template.name, 'shopify_status': data.get('status'), 'handle': data.get('handle'),
                'active': True}
        if images and template.image_1920:
            vals['image_checksum'] = checksum
        binding = self._connector_bind(store, data['id'], template, vals)
        by_options = {
            tuple((o['optionName'], o['name']) for o in variant['optionValues']): product
            for variant, product in zip(variants, products)
        }
        Variant = self.env['om.shopify.product']
        for node in (data.get('variants') or {}).get('nodes') or []:
            key = tuple((o['name'], o['value']) for o in node.get('selectedOptions') or [])
            product = by_options.get(key)
            if product:
                Variant._shopify_bind_variant(store, binding, {
                    'id': node['id'], 'title': ' / '.join(k[1] for k in key), 'sku': node.get('sku'),
                    'barcode': product.barcode, 'inventoryItem': node.get('inventoryItem') or {},
                }, product)
        if store.product_publish:
            store._shopify_publish(data['id'])
        return binding


class OmShopifyProduct(models.Model):
    """ A variant of a Shopify product, linked to an Odoo product. """
    _name = 'om.shopify.product'
    _description = 'Shopify Variant'
    _inherit = ['om.connector.binding.mixin']
    _order = 'store_id, template_binding_id, id'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'product_id'

    name = fields.Char(readonly=True)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    template_binding_id = fields.Many2one('om.shopify.product.template', string='Shopify Product',
                                          ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, ondelete='cascade', index=True)
    sku = fields.Char(string='SKU', readonly=True)
    barcode = fields.Char(readonly=True)
    inventory_item_gid = fields.Char(string='Inventory Item', readonly=True)
    tracked = fields.Boolean(string='Stock Tracked in Shopify', readonly=True)
    active = fields.Boolean(default=True)
    stock_rule = fields.Selection([
        ('actual', 'Actual Stock'),
        ('max', 'At Most'),
        ('percent', 'Percentage'),
        ('buffer', 'Keep Back'),
        ('fixed', 'Fixed Quantity'),
    ], string='Stock Sent', default='actual', required=True,
        help="Actual Stock: the stock of the warehouse.\nAt Most: the stock, at most the value.\n"
             "Percentage: this percent of the stock.\nKeep Back: the stock minus the value.\n"
             "Fixed Quantity: always the value, whatever the stock.")
    stock_value = fields.Float(string='Value')

    def _shopify_stock_quantity(self, quantity):
        self.ensure_one()
        quantity = max(quantity, 0.0)
        if self.stock_rule == 'max':
            quantity = min(quantity, self.stock_value)
        elif self.stock_rule == 'percent':
            quantity = math.floor(quantity * self.stock_value / 100.0)
        elif self.stock_rule == 'buffer':
            quantity = quantity - self.stock_value
        elif self.stock_rule == 'fixed':
            quantity = self.stock_value
        return max(int(quantity), 0)

    _store_external_unique = models.Constraint('unique (store_id, external_id)',
                                               "A Shopify variant is linked once per store.")

    @api.model
    def _shopify_match(self, store, variant):
        """ The Odoo product with the SKU or the barcode of ``variant``, as the store matches them. """
        Product = self.env['product.product'].with_context(active_test=False)
        domain_company = [('company_id', 'in', [False, store.company_id.id])]
        sku, barcode = (variant.get('sku') or '').strip(), (variant.get('barcode') or '').strip()
        if sku and store.product_match in ('sku', 'sku_barcode'):
            products = Product.search([('default_code', '=', sku)] + domain_company, limit=2)
            if len(products) == 1:
                return products
        if barcode and store.product_match in ('barcode', 'sku_barcode'):
            products = Product.search([('barcode', '=', barcode)] + domain_company, limit=2)
            if len(products) == 1:
                return products
        return None

    @api.model
    def _shopify_free_barcode(self, barcode):
        barcode = (barcode or '').strip()
        if barcode and not self.env['product.product'].with_context(active_test=False).search_count(
                [('barcode', '=', barcode)], limit=1):
            return barcode
        return False

    @api.model
    def _shopify_update_variant(self, product, variant):
        """ Fill the reference, barcode and weight of a product made from ``variant``. """
        vals = {}
        if variant.get('sku') and not product.default_code:
            vals['default_code'] = variant['sku']
        if not product.barcode and (barcode := self._shopify_free_barcode(variant.get('barcode'))):
            vals['barcode'] = barcode
        weight = ((variant.get('inventoryItem') or {}).get('measurement') or {}).get('weight') or {}
        if weight.get('value'):
            vals['weight'] = float(weight['value']) * WEIGHT_TO_KG.get(weight.get('unit'), 1.0)
        if vals:
            product.write(vals)

    @api.model
    def _shopify_bind_variant(self, store, template_binding, variant, product):
        item = variant.get('inventoryItem') or {}
        return self._connector_bind(store, variant['id'], product, {
            'template_binding_id': template_binding.id,
            'name': variant.get('title') if variant.get('title') != DEFAULT_OPTION[1] else template_binding.name,
            'sku': variant.get('sku') or False,
            'barcode': variant.get('barcode') or False,
            'inventory_item_gid': item.get('id'),
            'tracked': bool(item.get('tracked')),
            'active': True,
        })
