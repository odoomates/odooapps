from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _float(value):
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


class OmWoocommerceCoupon(models.Model):
    """ A coupon of a WooCommerce store, imported from it or made in Odoo and sent to it. """
    _name = 'om.woocommerce.coupon'
    _description = 'WooCommerce Coupon'
    _inherit = ['mail.thread']
    _order = 'store_id, code'
    _check_company_auto = True
    _rec_name = 'code'

    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True,
                               domain="[('state', '=', 'connected')]", tracking=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    woo_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False, index=True)
    active = fields.Boolean(default=True)
    code = fields.Char(required=True, tracking=True, help="The code the customer types at checkout.")
    description = fields.Char()
    discount_type = fields.Selection([
        ('percent', 'Percentage Discount'),
        ('fixed_cart', 'Fixed Cart Discount'),
        ('fixed_product', 'Fixed Product Discount'),
    ], required=True, default='percent', tracking=True)
    amount = fields.Float(tracking=True, help="The percentage, or the amount in the currency of the store.")
    free_shipping = fields.Boolean(help="The coupon gives free shipping, when a free shipping method needs a coupon.")
    date_expires = fields.Date(string='Expires On', tracking=True)
    minimum_amount = fields.Float(string='Minimum Spend')
    maximum_amount = fields.Float(string='Maximum Spend')
    individual_use = fields.Boolean(string='Individual Use Only', help="Not combined with other coupons.")
    exclude_sale_items = fields.Boolean(string='Exclude Sale Items')
    product_ids = fields.Many2many('product.product', 'om_woocommerce_coupon_product_rel', 'coupon_id', 'product_id',
                                   string='Products', help="Only these products get the discount. Empty: all.")
    excluded_product_ids = fields.Many2many('product.product', 'om_woocommerce_coupon_excluded_product_rel',
                                            'coupon_id', 'product_id', string='Excluded Products')
    email_restrictions = fields.Char(string='Allowed Emails',
                                     help="Only customers with these emails, separated by commas; * as a wildcard.")
    usage_limit = fields.Integer(help="How many times the coupon can be used. 0: no limit.")
    usage_limit_per_user = fields.Integer(string='Usage Limit per Customer', help="0: no limit.")
    usage_count = fields.Integer(string='Used', readonly=True, copy=False)
    sync_date = fields.Datetime(string='Last Sync', readonly=True, copy=False)
    order_count = fields.Integer(compute='_compute_order_count', string='Orders')

    _store_code_unique = models.Constraint('unique (store_id, code)', "A coupon code is used once per store.")

    def _compute_order_count(self):
        counts = dict(self.env['sale.order']._read_group([('woo_coupon_ids', 'in', self.ids)], ['woo_coupon_ids'],
                                                         ['__count']))
        for coupon in self:
            coupon.order_count = counts.get(coupon, 0)

    @api.onchange('code')
    def _onchange_code(self):
        if self.code:
            # WooCommerce keeps the codes in lower case
            self.code = self.code.strip().lower()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].strip().lower()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().lower()
        return super().write(vals)

    def action_open_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_woocommerce.om_woocommerce_sale_order_action')
        action['domain'] = [('woo_coupon_ids', 'in', self.ids)]
        return action

    def action_open_in_woocommerce(self):
        self.ensure_one()
        if not self.woo_id:
            raise UserError(_("Send the coupon to WooCommerce first."))
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': f'{self.store_id.site_url}/wp-admin/post.php?post={self.woo_id}&action=edit'}

    def action_woo_export(self):
        for coupon in self:
            coupon._woo_export()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': _("%(count)s coupon(s) sent to WooCommerce.", count=len(self)),
                           'type': 'success'}}

    def action_woo_delete(self):
        for coupon in self.filtered('woo_id'):
            coupon.store_id._woo_ensure_connected()
            coupon.store_id._woo_delete(f'coupons/{coupon.woo_id}', {'force': 'true'})
            coupon.message_post(body=_("Deleted in WooCommerce."))
        self.write({'woo_id': False, 'active': False})
        return True

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _woo_values(self):
        """ The coupon as WooCommerce takes it. """
        self.ensure_one()
        store = self.store_id
        return {
            'code': self.code,
            'description': self.description or '',
            'discount_type': self.discount_type,
            'amount': f'{self.amount:.2f}',
            'free_shipping': self.free_shipping,
            'date_expires': fields.Date.to_string(self.date_expires) if self.date_expires else None,
            'minimum_amount': f'{self.minimum_amount:.2f}' if self.minimum_amount else '',
            'maximum_amount': f'{self.maximum_amount:.2f}' if self.maximum_amount else '',
            'individual_use': self.individual_use,
            'exclude_sale_items': self.exclude_sale_items,
            'product_ids': store._woo_product_ids(self.product_ids),
            'excluded_product_ids': store._woo_product_ids(self.excluded_product_ids),
            'email_restrictions': [e.strip() for e in (self.email_restrictions or '').split(',') if e.strip()],
            'usage_limit': self.usage_limit or None,
            'usage_limit_per_user': self.usage_limit_per_user or None,
        }

    @api.model
    def _woo_odoo_values(self, store, data):
        """ The values of a coupon from the coupon ``data`` of WooCommerce. """
        discount_type = data.get('discount_type')
        expires = data.get('date_expires_gmt') or data.get('date_expires')
        return {
            'store_id': store.id,
            'woo_id': str(data['id']),
            'code': (data.get('code') or '').strip().lower(),
            'description': data.get('description') or False,
            'discount_type': discount_type if discount_type in dict(self._fields['discount_type'].selection)
            else 'fixed_cart',
            'amount': _float(data.get('amount')),
            'free_shipping': bool(data.get('free_shipping')),
            'date_expires': fields.Date.to_date(expires[:10]) if expires else False,
            'minimum_amount': _float(data.get('minimum_amount')),
            'maximum_amount': _float(data.get('maximum_amount')),
            'individual_use': bool(data.get('individual_use')),
            'exclude_sale_items': bool(data.get('exclude_sale_items')),
            'product_ids': [fields.Command.set(store._woo_odoo_products(data.get('product_ids')).ids)],
            'excluded_product_ids': [fields.Command.set(
                store._woo_odoo_products(data.get('excluded_product_ids')).ids)],
            'email_restrictions': ', '.join(data.get('email_restrictions') or []) or False,
            'usage_limit': data.get('usage_limit') or 0,
            'usage_limit_per_user': data.get('usage_limit_per_user') or 0,
            'usage_count': data.get('usage_count') or 0,
            'sync_date': fields.Datetime.now(),
            'active': True,
        }

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def _woo_export(self):
        """ Create or update the coupon in WooCommerce. """
        self.ensure_one()
        store = self.store_id
        store._woo_ensure_connected()
        vals = self._woo_values()
        data = store._woo_put(f'coupons/{self.woo_id}', vals) if self.woo_id else None
        if data is None:
            data = store._woo_post('coupons', vals)
        self.write({'woo_id': str(data['id']), 'usage_count': data.get('usage_count') or 0,
                    'sync_date': fields.Datetime.now()})
        return data

    @api.model
    def _woo_import_coupon(self, store, data):
        """ Create or update the coupon of ``data``; matched by its ID, then by its code. """
        if not data or not data.get('code'):
            return self.browse()
        coupon = self.with_context(active_test=False).search(
            [('store_id', '=', store.id), '|', ('woo_id', '=', str(data['id'])),
             ('code', '=', data['code'].strip().lower())], limit=1)
        vals = self._woo_odoo_values(store, data)
        if coupon:
            coupon.with_context(tracking_disable=True).write(vals)
            return coupon
        return self.with_context(tracking_disable=True).create(vals)

    @api.model
    def _connector_job_woo_coupon_webhook(self, job):
        payload = job.payload or {}
        data = payload if payload.get('code') else job.backend._woo_get(f"coupons/{payload['id']}")
        if not data:
            return _("Coupon %(id)s does not exist anymore", id=payload.get('id'))
        return self._woo_import_coupon(job.backend, data)

    @api.model
    def _connector_job_woo_coupon_deleted(self, job):
        coupons = self.search([('store_id', '=', job.backend.id), ('woo_id', '=', str(job.payload['id']))])
        coupons.write({'active': False, 'woo_id': False})
        return _("%(count)s coupon(s) archived", count=len(coupons))


class OmWoocommerceStoreCoupons(models.Model):
    _inherit = 'om.woocommerce.store'

    coupon_count = fields.Integer(compute='_compute_coupon_count', string='Coupons')
    coupon_last_sync = fields.Datetime(string='Coupons Imported On', readonly=True, copy=False)

    def _compute_coupon_count(self):
        counts = dict(self.env['om.woocommerce.coupon']._read_group([('store_id', 'in', self.ids)], ['store_id'],
                                                                     ['__count']))
        for store in self:
            store.coupon_count = counts.get(store, 0)

    def _woo_webhook_handlers(self):
        handlers = super()._woo_webhook_handlers()
        coupons = ('om.woocommerce.coupon', '_connector_job_woo_coupon_webhook')
        handlers.update({
            'coupon.created': coupons,
            'coupon.updated': coupons,
            'coupon.restored': coupons,
            'coupon.deleted': ('om.woocommerce.coupon', '_connector_job_woo_coupon_deleted'),
        })
        return handlers

    def _woo_product_ids(self, products):
        """ The WooCommerce IDs (products and variations) of the Odoo ``products`` in this store. """
        self.ensure_one()
        bindings = self.env['om.woocommerce.product'].search(
            [('store_id', '=', self.id), ('product_id', 'in', products.ids), ('active', '=', True)])
        return sorted({int(b.external_id) for b in bindings})

    def _woo_odoo_products(self, woo_ids):
        """ The Odoo products of WooCommerce IDs: a variation, a simple product, or every variation of
        a variable product. """
        self.ensure_one()
        ids = [str(i) for i in woo_ids or []]
        if not ids:
            return self.env['product.product']
        variants = self.env['om.woocommerce.product'].search(
            [('store_id', '=', self.id), '|', ('external_id', 'in', ids), ('parent_woo_id', 'in', ids)])
        return variants.product_id

    def action_woo_import_coupons(self):
        self._woo_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_woo_fetch_coupons', name=_("Import the coupons"))
        return self._woo_notification(_("The coupons are being imported: follow it in Jobs."), kind='info')

    def action_open_coupons(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Coupons of %(store)s", store=self.name),
            'res_model': 'om.woocommerce.coupon',
            'view_mode': 'list,form',
            'domain': [('store_id', '=', self.id)],
            'context': {'default_store_id': self.id},
        }

    @api.model
    def _connector_job_woo_fetch_coupons(self, job):
        store = job.backend
        Coupon = self.env['om.woocommerce.coupon']
        count = 0
        for data in store._woo_paginate('coupons'):
            Coupon._woo_import_coupon(store, data)
            count += 1
        store.coupon_last_sync = fields.Datetime.now()
        return _("%(count)s coupon(s) imported", count=count)
