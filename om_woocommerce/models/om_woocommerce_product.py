import base64
import hashlib
import logging
import math

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMPORTED_TYPES = ('simple', 'variable')


class OmWoocommerceProductTemplate(models.Model):
    """ A WooCommerce product, linked to an Odoo product template. """
    _name = 'om.woocommerce.product.template'
    _description = 'WooCommerce Product'
    _inherit = ['om.connector.binding.mixin']
    _order = 'store_id, name'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'product_tmpl_id'

    name = fields.Char(readonly=True)
    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product', required=True, ondelete='cascade',
                                      index=True)
    woo_type = fields.Selection([('simple', 'Simple'), ('variable', 'Variable')], string='Type', readonly=True)
    woo_status = fields.Selection([
        ('publish', 'Published'), ('draft', 'Draft'), ('pending', 'Pending Review'), ('private', 'Private'),
        ('future', 'Scheduled'), ('trash', 'Trash'), ('deleted', 'Deleted'),
    ], string='Status in WooCommerce', readonly=True)
    slug = fields.Char(readonly=True)
    variant_ids = fields.One2many('om.woocommerce.product', 'template_binding_id', string='Variants')
    active = fields.Boolean(default=True)
    image_checksum = fields.Char(readonly=True, copy=False, help="Checksum of the last image sent to WooCommerce.")

    _store_external_unique = models.Constraint('unique (store_id, external_id)',
                                               "A WooCommerce product is linked once per store.")

    def action_woo_export(self):
        for binding in self:
            binding.store_id._woo_enqueue_export(binding.product_tmpl_id)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': _("Export queued."), 'type': 'info'}}

    def action_woo_publish(self):
        return self._woo_set_status('publish')

    def action_woo_unpublish(self):
        return self._woo_set_status('draft')

    def _woo_set_status(self, status):
        for binding in self.filtered('active'):
            data = binding.store_id._woo_put(f'products/{binding.external_id}', {'status': status})
            if data is None:
                raise UserError(_("%(product)s does not exist anymore in WooCommerce.", product=binding.name))
            binding.woo_status = data.get('status') or status
        return True

    def action_open_in_woocommerce(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'{self.store_id.site_url}/wp-admin/post.php?post={self.external_id}&action=edit',
            'target': 'new',
        }

    def action_woo_import_again(self):
        for binding in self:
            binding.store_id._connector_enqueue(
                '_connector_job_woo_import_product', {'id': int(binding.external_id)},
                model_name=self._name, name=_("Product %(name)s", name=binding.name),
                dedupe_key=f'product:{binding.external_id}', priority=20)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': _("Import queued."), 'type': 'info'}}

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    @api.model
    def _connector_job_woo_import_product(self, job):
        return self._woo_import_product(job.backend, job.payload['id'])

    @api.model
    def _connector_job_woo_product_webhook(self, job):
        payload = job.payload or {}
        if payload.get('parent_id'):
            # a variation: the product it belongs to
            return self._woo_import_product(job.backend, payload['parent_id'], from_webhook=True)
        return self._woo_import_product(job.backend, payload['id'], from_webhook=True)

    @api.model
    def _connector_job_woo_product_deleted(self, job):
        return self._woo_unlink(job.backend, job.payload['id'])

    @api.model
    def _woo_unlink(self, store, woo_id, status='deleted'):
        """ The product was deleted or trashed in WooCommerce: its links are archived. """
        bindings = self.with_context(active_test=False)._connector_find(store, woo_id)
        bindings.write({'woo_status': status, 'active': False})
        bindings.variant_ids.write({'active': False})
        return _("%(count)s product(s) unlinked", count=len(bindings))

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @api.model
    def _woo_variants(self, store, data):
        """ The variants of the WooCommerce product ``data``, in one format: the product itself when it
        is simple, its variations when it is variable. """
        if data.get('type') != 'variable':
            return [self._woo_variant_values(data, data, parent=False)]
        return [self._woo_variant_values(variation, data, parent=True)
                for variation in store._woo_paginate(f"products/{data['id']}/variations")]

    @api.model
    def _woo_variant_values(self, item, product, parent):
        image = item.get('image') if parent else ((item.get('images') or [None])[0])
        return {
            'id': str(item['id']),
            'parent_id': str(product['id']) if parent else False,
            'sku': (item.get('sku') or '').strip(),
            'barcode': (item.get('global_unique_id') or '').strip(),
            'price': item.get('regular_price') or item.get('price') or '0',
            'weight': item.get('weight'),
            'manage_stock': item.get('manage_stock') is True,
            'image': (image or {}).get('src'),
            'options': [(a.get('name'), a.get('option')) for a in item.get('attributes') or [] if a.get('option')]
            if parent else [],
            'name': item.get('name') or product.get('name'),
            'meta_data': item.get('meta_data') if parent else [],
        }

    @api.model
    def _woo_import_product(self, store, woo_id, from_webhook=False):
        """ Import or update the WooCommerce product ``woo_id``: find or create the Odoo product of each
        variant, and link them. Gives the linked template, or a text when skipped. """
        data = store._woo_get(f'products/{woo_id}')
        if not data:
            return _("Product %(id)s does not exist anymore", id=woo_id)
        if data.get('type') not in IMPORTED_TYPES:
            return _("%(name)s is a %(type)s product: not imported", name=data.get('name'), type=data.get('type'))
        if data.get('status') == 'trash':
            return self._woo_unlink(store, data['id'], status='trash')
        variants = self._woo_variants(store, data)
        if not variants:
            return _("%(name)s has no variation yet: not imported", name=data.get('name'))
        binding = self.with_context(active_test=False)._connector_find(store, data['id'])
        variant_bindings = {b.external_id: b for b in binding.with_context(active_test=False).variant_ids}
        Variant = self.env['om.woocommerce.product']
        products = {}
        for variant in variants:
            product = variant_bindings[variant['id']].product_id if variant['id'] in variant_bindings else None
            products[variant['id']] = product or Variant._woo_match(store, variant)
        missing = [v for v in variants if not products[v['id']]]
        if missing:
            if not store.product_auto_create:
                if from_webhook and not binding:
                    return _("No Odoo product for %(name)s: not imported", name=data.get('name'))
                raise UserError(_(
                    "No Odoo product has the SKU or GTIN of these variants of %(name)s: %(variants)s. Create them, or "
                    "allow the store to create the products.", name=data.get('name'),
                    variants=', '.join(v['sku'] or v['barcode'] or v['id'] for v in missing)))
            template = next((p.product_tmpl_id for p in products.values() if p), None) or binding.product_tmpl_id
            products.update(self._woo_create_products(store, data, missing, template or None))
        templates = self.env['product.template'].union(*(p.product_tmpl_id for p in products.values()))
        template = binding.product_tmpl_id if binding.product_tmpl_id in templates else templates[:1]
        binding = self._connector_bind(store, str(data['id']), template, {
            'name': data.get('name'),
            'woo_type': data.get('type'),
            'woo_status': data.get('status') if data.get('status') in dict(self._fields['woo_status'].selection)
            else False,
            'slug': data.get('slug'),
            'active': True,
        })
        for variant in variants:
            Variant._woo_bind_variant(store, binding, variant, products[variant['id']])
            store._woo_apply_meta('variant', products[variant['id']], variant.get('meta_data'))
        store._woo_apply_meta('product', template, data.get('meta_data'))
        stale = binding.with_context(active_test=False).variant_ids.filtered(
            lambda b: b.external_id not in {v['id'] for v in variants})
        stale.write({'active': False})
        if store.product_import_images:
            self._woo_import_images(template, data, variants, products)
        return binding

    @api.model
    def _woo_create_products(self, store, data, variants, template=None):
        """ Create the Odoo products of ``variants`` of the WooCommerce product ``data``; in ``template``
        when given. Gives ``{variant id: product.product}``. """
        first = variants[0]
        new_template = template is None
        # no tracking: the attribute lines replace the variants the tracking of the template looks at
        Template = self.env['product.template'].with_context(tracking_disable=True)
        if new_template:
            simple = data.get('type') != 'variable'
            template = Template.create({
                'name': data.get('name') or first['name'],
                'type': 'consu',
                'is_storable': data.get('manage_stock') is True or any(v['manage_stock'] for v in variants),
                'list_price': float(first['price'] or 0.0),
                'company_id': False,
                'default_code': first['sku'] or False if simple else False,
                'barcode': self.env['om.woocommerce.product']._woo_free_barcode(first['barcode']) if simple else False,
            })
        template = template.with_context(tracking_disable=True)
        if data.get('type') != 'variable':
            product = template.product_variant_ids[:1]
            self.env['om.woocommerce.product']._woo_update_variant(store, product, first)
            return {first['id']: product}
        variants_before = template.product_variant_ids if not new_template else self.env['product.product']
        # one attribute per attribute of variations; a new attribute only makes the variants asked for
        Attribute = self.env['product.attribute']
        attribute_values = {}
        for attribute_data in data.get('attributes') or []:
            if not attribute_data.get('variation') or not attribute_data.get('name'):
                continue
            name = attribute_data['name']
            attribute = Attribute.search([('name', '=ilike', name), ('create_variant', '!=', 'no_variant')],
                                         limit=1) or Attribute.create({'name': name, 'create_variant': 'dynamic'})
            values = attribute_values.setdefault(name, {'attribute': attribute, 'values': {}})
            for value_name in attribute_data.get('options') or []:
                value = attribute.value_ids.filtered(lambda v: v.name.lower() == value_name.lower())[:1] or \
                    self.env['product.attribute.value'].create({'attribute_id': attribute.id, 'name': value_name})
                values['values'][value_name.lower()] = value
        for info in attribute_values.values():
            line = template.attribute_line_ids.filtered(lambda l: l.attribute_id == info['attribute'])
            wanted = self.env['product.attribute.value'].union(*info['values'].values())
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
            for name, option in variant['options']:
                info = attribute_values.get(name)
                value = info and info['values'].get((option or '').lower())
                if value:
                    ptavs |= template.attribute_line_ids.product_template_value_ids.filtered(
                        lambda v, value=value: v.product_attribute_value_id == value)
            product = template._create_product_variant(ptavs) if ptavs else template.product_variant_ids[:1]
            if not product:
                raise UserError(_("The variation %(variant)s of %(product)s cannot be created in Odoo (a variation "
                                  "for any value of an attribute is not supported).",
                                  variant=variant['sku'] or variant['id'], product=data.get('name')))
            self.env['om.woocommerce.product']._woo_update_variant(store, product, variant)
            result[variant['id']] = product
        # attributes that make every combination create variants WooCommerce does not have: removed,
        # as long as they were just made here
        made = self.env['product.product'].union(*result.values())
        bound = self.env['om.woocommerce.product'].with_context(active_test=False).search(
            [('product_id', 'in', template.with_context(active_test=False).product_variant_ids.ids)]).product_id
        (template.product_variant_ids - variants_before - made - bound).unlink()
        return result

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def _connector_job_woo_export_product(self, job):
        template = self.env['product.template'].browse(job.payload['template_id']).exists()
        if not template:
            return _("The product does not exist anymore")
        return self._woo_export_product(job.backend, template, job.payload.get('images', True))

    @api.model
    def _woo_description(self, template):
        if not template.description_sale:
            return ''
        return str(template.description_sale).replace('\n', '<br/>')

    @api.model
    def _woo_attribute_lines(self, template):
        """ ``(lines making variants, other lines)`` of ``template``. """
        lines = template.attribute_line_ids
        variant_lines = lines.filtered(lambda l: l.attribute_id.create_variant != 'no_variant')
        return variant_lines, lines - variant_lines

    @api.model
    def _woo_options(self, product, lines):
        """ ``[(attribute, value)]`` of ``product`` for the attribute ``lines``. """
        values = product.product_template_attribute_value_ids
        return [(line.attribute_id.name,
                 values.filtered(lambda v, line=line: v.attribute_line_id == line)[:1].name or '')
                for line in lines]

    @api.model
    def _woo_option_key(self, options):
        return tuple(sorted(((name or '').lower(), (value or '').lower()) for name, value in options))

    @api.model
    def _woo_stock_values(self, store, product, binding=None):
        if not product.is_storable:
            return {'manage_stock': False}
        quantity = product.with_context(warehouse_id=store.warehouse_id.id)[store.stock_field]
        if binding:
            quantity = binding._woo_stock_quantity(quantity)
        return {'manage_stock': True, 'stock_quantity': max(int(quantity), 0)}

    @api.model
    def _woo_product_values(self, store, product, binding=None):
        """ The values of a simple product or a variation: SKU, GTIN, prices, weight, stock. """
        vals = {
            'sku': product.default_code or '',
            **store._woo_prices(product),
            'weight': store._woo_weight(product.weight),
            **self._woo_stock_values(store, product, binding),
        }
        if product.barcode:
            vals['global_unique_id'] = product.barcode
        return vals

    @api.model
    def _woo_export_product(self, store, template, images=True):
        """ Create or update ``template`` in WooCommerce: a simple product, or a variable product with
        a variation per variant. Odoo is the master of the products it exports: its name, description,
        prices, weight, attributes and image replace those of WooCommerce, and the variations of
        WooCommerce that are not in Odoo are removed. Gives the binding. """
        store._woo_ensure_connected()
        model = self.with_context(active_test=False)
        binding = model.search([('store_id', '=', store.id), ('product_tmpl_id', '=', template.id)],
                              order='active desc, id desc', limit=1)
        variant_lines, other_lines = self._woo_attribute_lines(template)
        products = template.product_variant_ids
        variable = bool(variant_lines)
        cache = {}
        vals = {
            'name': template.name,
            'type': 'variable' if variable else 'simple',
            'description': self._woo_description(template),
        }
        if categories := store._woo_categories(template, cache):
            vals['categories'] = categories
        if tags := store._woo_tags(template, cache):
            vals['tags'] = tags
        meta = store._woo_meta_values('product', template)
        attributes = []
        if variable:
            used = products.product_template_attribute_value_ids
            attributes = [{'name': line.attribute_id.name, 'position': position, 'visible': True, 'variation': True,
                           'options': [v.name for v in line.product_template_value_ids if v in used]}
                          for position, line in enumerate(variant_lines)]
            vals['manage_stock'] = False
        else:
            variant_binding = binding.variant_ids[:1] if binding else None
            vals.update(self._woo_product_values(store, products[:1], variant_binding))
            meta += store._woo_meta_values('variant', products[:1])
        attributes += [{'name': line.attribute_id.name, 'position': len(attributes) + position, 'visible': True,
                        'variation': False, 'options': line.value_ids.mapped('name')}
                       for position, line in enumerate(other_lines)]
        if attributes or binding:
            vals['attributes'] = attributes
        if meta:
            vals['meta_data'] = meta
        checksum = binding.image_checksum if binding else False
        if images and template.image_1920 and store._woo_images_possible():
            new_checksum = hashlib.sha1(base64.b64decode(template.image_1920)).hexdigest()
            if new_checksum != checksum:
                media_id, checksum = store._woo_upload_image(template.image_1920, template.name)
                vals['images'] = [{'id': media_id}]
        data = None
        if binding:
            data = store._woo_put(f'products/{binding.external_id}', vals)
            if data is None:
                # removed from WooCommerce: made again, the old link archived
                binding._woo_unlink(store, binding.external_id)
                binding = model.browse()
                if 'images' not in vals and images and template.image_1920 and store._woo_images_possible():
                    media_id, checksum = store._woo_upload_image(template.image_1920, template.name)
                    vals['images'] = [{'id': media_id}]
        if data is None and not variable and vals.get('sku'):
            # a product of WooCommerce with this SKU, not linked yet: it is updated, not made twice
            found = store._woo_get('products', {'sku': vals['sku'], 'status': 'any', '_fields': 'id'}) or []
            if found:
                data = store._woo_put(f"products/{found[0]['id']}", vals)
        if data is None:
            data = store._woo_post('products', dict(vals, status=store.product_export_status))
        binding = model._connector_bind(store, str(data['id']), template, {
            'name': template.name,
            'woo_type': vals['type'],
            'woo_status': data.get('status') if data.get('status') in dict(self._fields['woo_status'].selection)
            else False,
            'slug': data.get('slug'),
            'active': True,
            'image_checksum': checksum,
        })
        Variant = model.env['om.woocommerce.product']
        if not variable:
            product = products[:1]
            exported = Variant._woo_bind_variant(store, binding, {
                'id': str(data['id']), 'parent_id': False, 'sku': vals.get('sku'), 'barcode': product.barcode,
                'manage_stock': vals.get('manage_stock'), 'options': []}, product)
        else:
            exported = self._woo_export_variations(store, binding, products, variant_lines, images)
        stale = binding.variant_ids - exported
        stale.write({'active': False})
        return binding

    @api.model
    def _woo_export_variations(self, store, binding, products, lines, images):
        """ Create, update and remove the variations of the variable product of ``binding``; gives
        the variant bindings. """
        Variant = self.env['om.woocommerce.product']
        path = f'products/{binding.external_id}/variations'
        existing = list(store._woo_paginate(path, {'_fields': 'id,attributes'}))
        existing_ids = {str(v['id']) for v in existing}
        by_key = {self._woo_option_key((a.get('name'), a.get('option')) for a in v.get('attributes') or []):
                  str(v['id']) for v in existing}
        bound = {b.product_id: b for b in binding.with_context(active_test=False).variant_ids}
        updates, creates, used = [], [], set()
        for product in products:
            options = self._woo_options(product, lines)
            variant_binding = bound.get(product)
            item = {
                **self._woo_product_values(store, product, variant_binding),
                'attributes': [{'name': name, 'option': value} for name, value in options],
            }
            if meta := store._woo_meta_values('variant', product):
                item['meta_data'] = meta
            checksum = variant_binding.image_checksum if variant_binding else False
            if images and product.image_variant_1920 and store._woo_images_possible():
                new_checksum = hashlib.sha1(base64.b64decode(product.image_variant_1920)).hexdigest()
                if new_checksum != checksum:
                    media_id, checksum = store._woo_upload_image(product.image_variant_1920, product.display_name)
                    item['image'] = {'id': media_id}
            woo_id = variant_binding.external_id if variant_binding and variant_binding.external_id in existing_ids \
                else by_key.get(self._woo_option_key(options))
            if woo_id and woo_id not in used:
                used.add(woo_id)
                updates.append((product, options, checksum, dict(item, id=int(woo_id))))
            else:
                creates.append((product, options, checksum, item))
        result = Variant.browse()
        for todo, answers in (
                (updates, store._woo_batch(path, update=[u[3] for u in updates]) if updates else []),
                (creates, store._woo_batch(path, create=[c[3] for c in creates]) if creates else [])):
            for (product, options, checksum, item), answer in zip(todo, answers):
                variant_binding = Variant._woo_bind_variant(store, binding, {
                    'id': str(answer['id']), 'parent_id': binding.external_id, 'sku': item.get('sku'),
                    'barcode': product.barcode, 'manage_stock': item.get('manage_stock'), 'options': options,
                }, product)
                variant_binding.image_checksum = checksum
                result |= variant_binding
        if removed := sorted(existing_ids - used - {r.external_id for r in result}, key=int):
            store._woo_batch(path, delete=[int(r) for r in removed])
        return result

    @api.model
    def _woo_download(self, url):
        if not url:
            return None
        try:
            response = requests.get(url, timeout=15)
        except requests.RequestException as e:
            _logger.info("Image %s not downloaded: %s", url, e)
            return None
        if response.ok and response.content and len(response.content) <= MAX_IMAGE_BYTES:
            return base64.b64encode(response.content)
        return None

    @api.model
    def _woo_import_images(self, template, data, variants, products):
        """ The main image, the gallery (in the eCommerce gallery when it is installed) and the image of
        each variation, for the Odoo products without one. """
        urls = [image.get('src') for image in data.get('images') or [] if image.get('src')]
        main_url = urls[0] if urls else None
        if not template.image_1920 and (image := self._woo_download(main_url)):
            template.image_1920 = image
        if 'product.image' in self.env and 'product_tmpl_id' in self.env['product.image']._fields \
                and not template.product_template_image_ids:
            for url in urls[1:]:
                if image := self._woo_download(url):
                    self.env['product.image'].create({'product_tmpl_id': template.id, 'name': template.name,
                                                      'image_1920': image})
        if len(products) > 1:
            for variant in variants:
                product = products.get(variant['id'])
                url = variant['image']
                if product and url and url != main_url and not product.image_variant_1920 \
                        and (image := self._woo_download(url)):
                    product.image_variant_1920 = image


class OmWoocommerceProduct(models.Model):
    """ A WooCommerce simple product or variation, linked to an Odoo product. """
    _name = 'om.woocommerce.product'
    _description = 'WooCommerce Variant'
    _inherit = ['om.connector.binding.mixin']
    _order = 'store_id, template_binding_id, id'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'product_id'

    name = fields.Char(readonly=True)
    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    template_binding_id = fields.Many2one('om.woocommerce.product.template', string='WooCommerce Product',
                                          ondelete='cascade', index=True)
    parent_woo_id = fields.Char(string='Parent Product', readonly=True,
                                help="For a variation: the ID of its variable product in WooCommerce.")
    product_id = fields.Many2one('product.product', string='Product', required=True, ondelete='cascade', index=True)
    sku = fields.Char(string='SKU', readonly=True)
    barcode = fields.Char(string='GTIN', readonly=True)
    manage_stock = fields.Boolean(string='Stock Managed in WooCommerce', readonly=True)
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
    image_checksum = fields.Char(readonly=True, copy=False, help="Checksum of the last image sent to WooCommerce.")

    _store_external_unique = models.Constraint('unique (store_id, external_id)',
                                               "A WooCommerce variant is linked once per store.")

    def _woo_stock_quantity(self, quantity):
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

    @api.model
    def _woo_match(self, store, variant):
        """ The Odoo product with the SKU or the GTIN of ``variant``, as the store matches them. """
        Product = self.env['product.product'].with_context(active_test=False)
        domain_company = [('company_id', 'in', [False, store.company_id.id])]
        sku, barcode = variant.get('sku') or '', variant.get('barcode') or ''
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
    def _woo_free_barcode(self, barcode):
        barcode = (barcode or '').strip()
        if barcode and not self.env['product.product'].with_context(active_test=False).search_count(
                [('barcode', '=', barcode)], limit=1):
            return barcode
        return False

    @api.model
    def _woo_update_variant(self, store, product, variant):
        """ Fill the reference, barcode and weight of a product made from ``variant``. """
        vals = {}
        if variant.get('sku') and not product.default_code:
            vals['default_code'] = variant['sku']
        if not product.barcode and (barcode := self._woo_free_barcode(variant.get('barcode'))):
            vals['barcode'] = barcode
        if weight := store._woo_weight_kg(variant.get('weight')):
            vals['weight'] = weight
        if vals:
            product.write(vals)

    @api.model
    def _woo_bind_variant(self, store, template_binding, variant, product):
        return self._connector_bind(store, variant['id'], product, {
            'template_binding_id': template_binding.id,
            'parent_woo_id': variant.get('parent_id') or False,
            'name': ' / '.join(option for _name, option in variant['options']) or template_binding.name,
            'sku': variant.get('sku') or False,
            'barcode': variant.get('barcode') or False,
            'manage_stock': variant.get('manage_stock'),
            'active': True,
        })
