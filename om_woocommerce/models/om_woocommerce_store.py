import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.om_connector_base.tools import crypto

from ..tools import WooAuthError, WooClient, WooUserError, normalize_site_url

_logger = logging.getLogger(__name__)

WEBHOOK_ROUTE = '/om_woocommerce/webhook/%s'
WEIGHT_TO_KG = {'kg': 1.0, 'g': 0.001, 'lbs': 0.45359237, 'oz': 0.028349523125}


class OmWoocommerceStore(models.Model):
    """ A WooCommerce site connected to Odoo. """
    _name = 'om.woocommerce.store'
    _description = 'WooCommerce Store'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'om.connector.backend.mixin']
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    site_url = fields.Char(string='Site Address', required=True, tracking=True,
                           help="The address of the WordPress site, e.g. https://shop.example.com")
    state = fields.Selection([
        ('draft', 'Not Connected'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], default='draft', required=True, readonly=True, tracking=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)

    # Credentials, stored encrypted
    consumer_key = fields.Char(groups='om_woocommerce.group_om_woocommerce_manager', copy=False,
                               compute='_compute_secrets', inverse='_inverse_consumer_key',
                               help="WooCommerce > Settings > Advanced > REST API: a key with Read/Write permission.")
    consumer_secret = fields.Char(groups='om_woocommerce.group_om_woocommerce_manager', copy=False,
                                  compute='_compute_secrets', inverse='_inverse_consumer_secret')
    webhook_secret = fields.Char(groups='om_woocommerce.group_om_woocommerce_manager', copy=False,
                                 compute='_compute_secrets', inverse='_inverse_webhook_secret',
                                 help="Signs the webhooks WooCommerce sends to Odoo. Made by Odoo.")
    consumer_key_encrypted = fields.Char(groups='base.group_system', copy=False)
    consumer_secret_encrypted = fields.Char(groups='base.group_system', copy=False)
    webhook_secret_encrypted = fields.Char(groups='base.group_system', copy=False)
    wp_username = fields.Char(string='WordPress User', groups='om_woocommerce.group_om_woocommerce_manager',
                              help="A WordPress user allowed to upload files (an Administrator or a Shop Manager): "
                                   "for the images of the exported products.")
    wp_app_password = fields.Char(string='Application Password', copy=False,
                                  groups='om_woocommerce.group_om_woocommerce_manager',
                                  compute='_compute_secrets', inverse='_inverse_wp_app_password',
                                  help="Users > Profile > Application Passwords in WordPress. Empty: the products "
                                       "are exported without images.")
    wp_app_password_encrypted = fields.Char(groups='base.group_system', copy=False)
    # authorization in WordPress (wc-auth): the store waiting for its keys, and what to do next
    auth_state_hash = fields.Char(groups='base.group_system', copy=False)
    auth_state_expires = fields.Datetime(groups='base.group_system', copy=False)
    auth_state_uid = fields.Many2one('res.users', groups='base.group_system', copy=False)
    setup_pending = fields.Char(groups='base.group_system', copy=False,
                                help="The first imports to start once the store is connected.")
    secret_key_source = fields.Selection([
        ('config', 'Odoo configuration file (om_connector_key)'),
        ('database', 'Secret of the database'),
    ], string='Encryption Key', compute='_compute_secret_key_source')
    query_auth = fields.Boolean(
        string='Credentials in the Address',
        help="Sends the key and secret in the address of each call instead of the Authorization header: for the "
             "servers that drop this header (WooCommerce answers 401 although the key is right).")
    rest_route = fields.Boolean(
        string='Plain Permalinks', readonly=True, copy=False,
        help="The site has no pretty permalinks: the API is reached through ?rest_route=. Found when connecting.")

    # Site details, read when connecting
    site_name = fields.Char(readonly=True, copy=False)
    site_currency_id = fields.Many2one('res.currency', string='Store Currency', readonly=True, copy=False)
    site_timezone = fields.Char(string='Site Timezone', readonly=True, copy=False)
    weight_unit = fields.Selection([('kg', 'kg'), ('g', 'g'), ('lbs', 'lbs'), ('oz', 'oz')],
                                   string='Weight Unit', default='kg', readonly=True, copy=False)

    # Webhooks
    webhook_base_url = fields.Char(
        string='Odoo Public URL',
        help="The address WooCommerce sends the webhooks to, when it is not the address of this Odoo (a tunnel, a "
             "proxy). Empty: the web.base.url of Odoo.")
    webhook_url = fields.Char(string='Webhook Address', compute='_compute_webhook_url')
    webhook_ids = fields.One2many('om.woocommerce.webhook', 'store_id', string='Webhooks')
    webhook_count = fields.Integer(compute='_compute_webhook_count')

    # Orders
    warehouse_id = fields.Many2one('stock.warehouse', required=True, check_company=True,
                                   default=lambda self: self._default_warehouse(),
                                   help="The warehouse of the orders, and the one whose stock is sent.")
    team_id = fields.Many2one('crm.team', string='Sales Team', check_company=True)
    user_id = fields.Many2one('res.users', string='Salesperson', domain="[('share', '=', False)]")
    responsible_id = fields.Many2one('res.users', string='Responsible', domain="[('share', '=', False)]",
                                     help="Gets an activity when a job fails or an order waits.")
    gateway_ids = fields.One2many('om.woocommerce.gateway', 'store_id', string='Payment Methods')
    workflow_id = fields.Many2one('om.connector.order.workflow', string='Default Workflow', check_company=True,
                                  help="What Odoo does with the orders paid with a payment method it meets the first "
                                       "time: confirm, invoice, register the payment.")
    order_rule_ids = fields.One2many('om.woocommerce.order.rule', 'store_id', string='Order Rules')
    order_status_ids = fields.Many2many(
        'om.woocommerce.order.status', string='Statuses to Import',
        default=lambda self: self.env['om.woocommerce.order.status'].search([('code', 'in', (
            'processing', 'completed', 'on-hold'))]),
        help="The orders in these statuses are imported; an order imported before follows its status whatever it "
             "is. Pending and failed orders are not paid yet.")
    order_auto_import = fields.Boolean(string='Import Orders Automatically', default=True,
                                       help="Every 15 minutes, besides the webhooks.")
    order_import_from = fields.Datetime(string='Import Orders From',
                                        help="The orders changed before this date are not imported.")
    order_last_sync = fields.Datetime(string='Orders Imported On', readonly=True, copy=False)
    order_use_woo_number = fields.Boolean(string='Use the WooCommerce Order Number',
                                          help="The sale orders are named after the WooCommerce order number.")
    order_prefix = fields.Char(string='Order Prefix', help="Put before the WooCommerce order number, e.g. WC.")
    order_deliver_completed = fields.Boolean(
        string='Deliver Completed Orders', default=True,
        help="An order already completed in WooCommerce when it reaches Odoo is delivered in Odoo.")
    tax_mode = fields.Selection([
        ('woocommerce', 'Taxes of WooCommerce'),
        ('odoo', 'Taxes of Odoo'),
    ], string='Order Taxes', default='woocommerce', required=True,
        help="Taxes of WooCommerce: each line gets an Odoo tax of the rate charged by WooCommerce, found or created.\n"
             "Taxes of Odoo: each line gets the taxes of its product and the fiscal position of the customer.")
    tax_account_id = fields.Many2one('account.account', string='Account of the New Taxes', check_company=True,
                                     help="The tax account of the taxes made for the WooCommerce rates. Empty: the "
                                          "account of the tax group.")
    shipping_product_id = fields.Many2one('product.product', string='Shipping Product', required=True,
                                          default=lambda self: self.env.ref('om_woocommerce.product_woo_shipping',
                                                                            raise_if_not_found=False))
    fee_product_id = fields.Many2one('product.product', string='Fee Product', required=True,
                                     default=lambda self: self.env.ref('om_woocommerce.product_woo_fee',
                                                                       raise_if_not_found=False))
    custom_product_id = fields.Many2one('product.product', string='Product of Unknown Items', required=True,
                                        default=lambda self: self.env.ref('om_woocommerce.product_woo_custom',
                                                                          raise_if_not_found=False),
                                        help="For the order lines whose product was removed from WooCommerce.")
    refund_adjustment_product_id = fields.Many2one(
        'product.product', string='Refund Adjustment Product', required=True,
        default=lambda self: self.env.ref('om_woocommerce.product_woo_refund_adjustment', raise_if_not_found=False))
    order_count = fields.Integer(compute='_compute_counts', string='Orders')

    # Refunds
    refund_import = fields.Boolean(string='Import Refunds', default=True,
                                   help="A refund made in WooCommerce becomes a paid credit note.")
    refund_create_return = fields.Boolean(string='Return Refunded Products',
                                          help="Also returns the refunded products to stock.")
    refund_validate_return = fields.Boolean(string='Validate the Return')
    refund_api = fields.Boolean(
        string='Refund through the Payment Gateway',
        help="A credit note refunded from Odoo also refunds the money through the payment gateway of the order, when "
             "it can (Stripe, PayPal…). Unticked: the refund is recorded in WooCommerce only.")
    refund_restock = fields.Boolean(string='Restock in WooCommerce', default=True,
                                    help="A credit note refunded from Odoo puts its products back in stock in "
                                         "WooCommerce.")

    # Products
    product_match = fields.Selection([
        ('sku', 'SKU'),
        ('barcode', 'GTIN, UPC, EAN or ISBN'),
        ('sku_barcode', 'SKU, then GTIN'),
    ], string='Match Products On', default='sku_barcode', required=True,
        help="How a WooCommerce product finds its Odoo product: its SKU is the Internal Reference, its GTIN the "
             "Barcode.")
    product_auto_create = fields.Boolean(string='Create Missing Products', default=True,
                                         help="Creates the Odoo products of the WooCommerce products without one.")
    product_import_images = fields.Boolean(string='Import Images', default=True)
    product_auto_import = fields.Boolean(string='Import Products Every Day', default=True)
    product_last_sync = fields.Datetime(string='Products Imported On', readonly=True, copy=False)
    product_count = fields.Integer(compute='_compute_counts', string='Products')

    # Product export and prices
    product_export_status = fields.Selection([
        ('draft', 'Draft'), ('pending', 'Pending Review'), ('private', 'Private'), ('publish', 'Published'),
    ], string='Status of Exported Products', default='draft', required=True,
        help="The status of the products created in WooCommerce by an export; an export does not change the status "
             "of a product already in WooCommerce.")
    product_export_category = fields.Boolean(
        string='Send the Category', default=True,
        help="The product category of Odoo becomes a WooCommerce category, with its parents (the top category of "
             "Odoo, such as All, left out).")
    product_export_tags = fields.Boolean(string='Send the Tags', default=True,
                                         help="The product tags of Odoo become WooCommerce tags.")
    price_pricelist_id = fields.Many2one('product.pricelist', string='Price List', check_company=True,
                                         help="The prices customers pay in WooCommerce. Empty: the sales price of the "
                                              "products.")
    compare_pricelist_id = fields.Many2one(
        'product.pricelist', string='Regular Price List', check_company=True,
        help="When it gives a higher price, that price is the regular price of WooCommerce and the price above the "
             "sale price: WooCommerce shows the product on sale.")
    price_auto_export = fields.Boolean(string='Send Prices Every Day',
                                       help="Sends the prices of the linked products to WooCommerce every day.")
    price_last_sync = fields.Datetime(string='Prices Sent On', readonly=True, copy=False)

    # Stock
    stock_export = fields.Boolean(string='Send Stock to WooCommerce', default=True,
                                  help="Sends the stock of the warehouse every 15 minutes.")
    stock_field = fields.Selection([
        ('free_qty', 'Free to Use (on hand minus reserved)'),
        ('qty_available', 'On Hand'),
        ('virtual_available', 'Forecasted'),
    ], string='Stock Sent', default='free_qty', required=True)
    stock_last_sync = fields.Datetime(string='Stock Sent On', readonly=True, copy=False)
    stock_import_apply = fields.Boolean(string='Apply the Imported Stock',
                                        help="Import Stock sets the counted quantities; ticked, it also applies them.")

    # Fulfillment
    fulfillment_push = fields.Boolean(
        string='Complete Delivered Orders', default=True,
        help="When an order is fully delivered in Odoo, it is completed in WooCommerce (which emails the customer).")
    fulfillment_tracking = fields.Selection([
        ('none', 'Not Sent'),
        ('note', 'Note to the Customer'),
        ('plugin', 'WooCommerce Shipment Tracking'),
    ], string='Tracking Numbers', default='note', required=True,
        help="Note to the Customer: the carrier and the tracking number in a note of the order, emailed by "
             "WooCommerce.\nWooCommerce Shipment Tracking: for the sites with this extension.")

    customer_last_sync = fields.Datetime(string='Customers Imported On', readonly=True, copy=False)
    shipping_ids = fields.One2many('om.woocommerce.shipping', 'store_id', string='Shipping Methods')

    _site_url_company_unique = models.Constraint(
        'unique (site_url, company_id)', "This site is already connected in this company.")

    @api.model
    def _default_warehouse(self):
        return self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)

    def _compute_counts(self):
        products = dict(self.env['om.woocommerce.product.template']._read_group(
            [('store_id', 'in', self.ids)], ['store_id'], ['__count']))
        orders = dict(self.env['sale.order']._read_group(
            [('woo_store_id', 'in', self.ids)], ['woo_store_id'], ['__count']))
        for store in self:
            store.product_count = products.get(store, 0)
            store.order_count = orders.get(store, 0)

    @api.depends('consumer_key_encrypted', 'consumer_secret_encrypted', 'webhook_secret_encrypted',
                 'wp_app_password_encrypted')
    def _compute_secrets(self):
        for store in self:
            sudo = store.sudo()
            store.consumer_key = crypto.decrypt(self.env, sudo.consumer_key_encrypted)
            store.consumer_secret = crypto.decrypt(self.env, sudo.consumer_secret_encrypted)
            store.webhook_secret = crypto.decrypt(self.env, sudo.webhook_secret_encrypted)
            store.wp_app_password = crypto.decrypt(self.env, sudo.wp_app_password_encrypted)

    def _inverse_consumer_key(self):
        for store in self:
            store.sudo().consumer_key_encrypted = crypto.encrypt(self.env, (store.consumer_key or '').strip())

    def _inverse_consumer_secret(self):
        for store in self:
            store.sudo().consumer_secret_encrypted = crypto.encrypt(self.env, (store.consumer_secret or '').strip())

    def _inverse_webhook_secret(self):
        for store in self:
            store.sudo().webhook_secret_encrypted = crypto.encrypt(self.env, store.webhook_secret)

    def _inverse_wp_app_password(self):
        for store in self:
            # WordPress shows the password in groups of four: the spaces are optional
            store.sudo().wp_app_password_encrypted = crypto.encrypt(self.env, (store.wp_app_password or '').strip())

    def _compute_secret_key_source(self):
        source = crypto.key_source(self.env)
        for store in self:
            store.secret_key_source = source

    @api.depends('webhook_base_url')
    def _compute_webhook_url(self):
        base_url = self.get_base_url()
        for store in self:
            root = (store.webhook_base_url or base_url).rstrip('/')
            store.webhook_url = f'{root}{WEBHOOK_ROUTE % store.id}' if store.id else False

    @api.depends('webhook_ids')
    def _compute_webhook_count(self):
        for store in self:
            store.webhook_count = len(store.webhook_ids)

    @api.onchange('site_url')
    def _onchange_site_url(self):
        if self.site_url:
            self.site_url = normalize_site_url(self.site_url)
            if not self.name:
                host = self.site_url.split('://', 1)[-1].split('/')[0]
                self.name = host.removeprefix('www.').split('.')[0].replace('-', ' ').title()

    @api.constrains('site_url')
    def _check_site_url(self):
        for store in self:
            if not (store.site_url or '').startswith('https://'):
                raise ValidationError(_("WooCommerce accepts a consumer key over https only: %(url)s is not an https "
                                        "address.", url=store.site_url))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('site_url'):
                vals['site_url'] = normalize_site_url(vals['site_url'])
        stores = super().create(vals_list)
        for store in stores:
            if not store.sudo().webhook_secret:
                store.sudo().webhook_secret = secrets.token_urlsafe(32)
            if not store.workflow_id:
                store.workflow_id = store._woo_default_workflow()
        return stores

    def write(self, vals):
        if vals.get('site_url'):
            vals['site_url'] = normalize_site_url(vals['site_url'])
        return super().write(vals)

    def _woo_default_workflow(self):
        self.ensure_one()
        journal = self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.company_id.id)], limit=1)
        return self.env['om.connector.order.workflow'].sudo().create({
            'name': _("%(store)s: paid orders", store=self.name),
            'company_id': self.company_id.id,
            'journal_id': journal.id,
            'register_payment': bool(journal),
        })

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def _woo_client(self, rest_route=None):
        self.ensure_one()
        store = self.sudo()
        if not store.consumer_key or not store.consumer_secret:
            raise UserError(_("Set the consumer key and secret of %(store)s.", store=store.name))
        return WooClient(store.site_url, store.consumer_key, store.consumer_secret, query_auth=store.query_auth,
                         rest_route=store.rest_route if rest_route is None else rest_route)

    def _woo_get(self, path, params=None):
        return self._woo_client().get(path, params)

    def _woo_post(self, path, data=None):
        return self._woo_client().post(path, data)

    def _woo_put(self, path, data=None):
        return self._woo_client().put(path, data)

    def _woo_delete(self, path, params=None):
        return self._woo_client().delete(path, params)

    def _woo_paginate(self, path, params=None):
        return self._woo_client().paginate(path, params)

    def _woo_batch(self, path, update=None, create=None, delete=None):
        return self._woo_client().batch(path, update=update, create=create, delete=delete)

    @staticmethod
    def _woo_date(value):
        """ An Odoo datetime (UTC) for the ``*_after`` filters of WooCommerce, with ``dates_are_gmt``. """
        return fields.Datetime.to_datetime(value).strftime('%Y-%m-%dT%H:%M:%S')

    @staticmethod
    def _woo_parse_date(value):
        """ A ``*_gmt`` date of WooCommerce (``2026-11-16T09:00:00``) as an Odoo datetime. """
        if not value:
            return False
        return fields.Datetime.to_datetime(value[:19].replace('T', ' '))

    def _woo_weight_kg(self, value):
        self.ensure_one()
        try:
            return float(value or 0.0) * WEIGHT_TO_KG.get(self.weight_unit or 'kg', 1.0)
        except ValueError:
            return 0.0

    def _woo_weight(self, kg):
        """ A weight in kg as WooCommerce takes it: a text in the weight unit of the site. """
        self.ensure_one()
        if not kg:
            return ''
        return f'{kg / WEIGHT_TO_KG.get(self.weight_unit or "kg", 1.0):.3f}'.rstrip('0').rstrip('.')

    # ------------------------------------------------------------------
    # Product export: prices, categories, tags, images
    # ------------------------------------------------------------------

    def _woo_prices(self, product):
        """ ``{regular_price, sale_price}`` of ``product`` for WooCommerce: the price of the price list,
        as a sale price under the regular price list when that one is higher. """
        self.ensure_one()
        price = self.price_pricelist_id._get_product_price(product, 1.0) if self.price_pricelist_id \
            else product.lst_price
        regular = self.compare_pricelist_id._get_product_price(product, 1.0) if self.compare_pricelist_id else 0.0
        if regular > price:
            return {'regular_price': f'{regular:.2f}', 'sale_price': f'{price:.2f}'}
        return {'regular_price': f'{price:.2f}', 'sale_price': ''}

    def _woo_term(self, path, name, parent=0, cache=None):
        """ The id of the category or tag (``path``: products/categories, products/tags) named
        ``name`` (under ``parent`` for a category), found or created in WooCommerce. """
        self.ensure_one()
        key = (path, name.lower(), parent)
        if cache is not None and key in cache:
            return cache[key]
        params = {'search': name}
        if path == 'products/categories':
            params['parent'] = parent
        term = next((t for t in self._woo_paginate(path, params)
                     if (t.get('name') or '').lower() == name.lower()
                     and (path != 'products/categories' or (t.get('parent') or 0) == parent)), None)
        if not term:
            vals = {'name': name, 'parent': parent} if path == 'products/categories' else {'name': name}
            term = self._woo_post(path, vals) or {}
        if cache is not None:
            cache[key] = term.get('id')
        return term.get('id')

    def _woo_categories(self, template, cache=None):
        """ ``[{id}]``: the WooCommerce category of the Odoo category of ``template``. """
        self.ensure_one()
        category = template.categ_id
        if not self.product_export_category or not category.parent_id:
            return []
        names = []
        while category.parent_id:
            names.insert(0, category.name)
            category = category.parent_id
        parent = 0
        for name in names:
            parent = self._woo_term('products/categories', name, parent, cache)
        return [{'id': parent}] if parent else []

    def _woo_tags(self, template, cache=None):
        self.ensure_one()
        if not self.product_export_tags or 'product_tag_ids' not in template._fields:
            return []
        return [{'id': tag_id} for tag in template.product_tag_ids
                if (tag_id := self._woo_term('products/tags', tag.name, cache=cache))]

    def _woo_images_possible(self):
        self.ensure_one()
        store = self.sudo()
        return bool(store.wp_username and store.wp_app_password)

    def _woo_upload_image(self, image, name):
        """ Upload ``image`` (the bytes of an Odoo image) to the media library of WordPress; gives
        ``(media id, checksum)``. """
        self.ensure_one()
        content = bytes(image)
        mimetype = 'image/png' if content[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
        slug = ''.join(c if c.isalnum() else '-' for c in (name or 'product').lower()).strip('-')[:60] or 'product'
        filename = f"{slug}.{'png' if mimetype == 'image/png' else 'jpg'}"
        store = self.sudo()
        media = self._woo_client().upload_media(store.wp_username, store.wp_app_password.replace(' ', ''),
                                                filename, content, mimetype)
        return media['id'], hashlib.sha1(content).hexdigest()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _woo_find_api(self):
        """ The index of the REST API of the site (no credentials needed); with pretty permalinks, or
        else through ``?rest_route=``. Sets ``rest_route``. """
        self.ensure_one()
        errors = []
        for rest_route in (False, True):
            client = self._woo_client(rest_route=rest_route)
            try:
                index = client.get('', namespace='', auth=False)
            except WooUserError as e:
                errors.append(str(e))
                continue
            if isinstance(index, dict) and 'wc/v3' in (index.get('namespaces') or []):
                if self.rest_route != rest_route:
                    self.rest_route = rest_route
                return index
            if isinstance(index, dict) and index.get('namespaces') is not None:
                raise UserError(_("%(url)s is a WordPress site without WooCommerce (or with WooCommerce older than "
                                  "3.5): activate WooCommerce.", url=self.site_url))
        raise UserError(_("No WordPress REST API at %(url)s. %(errors)s", url=self.site_url,
                          errors=' '.join(errors)))

    def action_woo_connect(self):
        """ Check the credentials, read the details of the site and subscribe to the webhooks. """
        for store in self:
            try:
                index = store._woo_find_api()
                currency = (store._woo_get('settings/general/woocommerce_currency') or {}).get('value')
                weight = (store._woo_get('settings/products/woocommerce_weight_unit') or {}).get('value')
            except UserError as e:
                store.write({'state': 'error', 'last_error': str(e)})
                return self._woo_notification(str(e), kind='danger')
            currency = self.env['res.currency'].with_context(active_test=False).search([('name', '=', currency)],
                                                                                      limit=1)
            store.write({
                'state': 'connected',
                'last_error': False,
                'site_name': index.get('name') or store.site_url,
                'site_timezone': index.get('timezone_string') or False,
                'site_currency_id': currency.id,
                'weight_unit': weight if weight in WEIGHT_TO_KG else 'kg',
            })
            store.message_post(body=_("Connected to %(site)s.", site=index.get('name') or store.site_url))
            if store._woo_webhooks_possible():
                store.action_woo_sync_webhooks()
            else:
                store.message_post(body=_(
                    "No webhooks: WooCommerce sends them to an https address, and %(url)s is not one. Set the Odoo "
                    "Public URL of the store, then click Sync Webhooks. The scheduled imports still run.",
                    url=store.webhook_url))
        return self._woo_notification(_("Connected to WooCommerce."))

    # ------------------------------------------------------------------
    # Authorization in WordPress (wc-auth)
    # ------------------------------------------------------------------

    def _woo_odoo_root(self):
        self.ensure_one()
        return (self.webhook_base_url or self.get_base_url()).rstrip('/')

    def action_woo_authorize(self):
        """ Open the page of WordPress where an administrator approves Odoo: WooCommerce then sends
        a REST API key to Odoo, with no key to copy. """
        self.ensure_one()
        if not self._woo_odoo_root().startswith('https://'):
            raise UserError(_("WooCommerce sends the key to an https address only, and %(url)s is not one. Set the "
                              "Odoo Public URL of the store, or paste a REST API key instead.",
                              url=self._woo_odoo_root()))
        return {'type': 'ir.actions.act_url', 'url': f'/om_woocommerce/auth/start/{self.id}', 'target': 'self'}

    def _woo_authorize_url(self):
        """ A new state for this authorization, and the page of WordPress that asks for it. """
        self.ensure_one()
        state = secrets.token_urlsafe(32)
        self.sudo().write({
            'auth_state_hash': hashlib.sha256(state.encode()).hexdigest(),
            'auth_state_expires': fields.Datetime.now() + timedelta(minutes=30),
            'auth_state_uid': self.env.uid,
        })
        root = self._woo_odoo_root()
        # the query form of the endpoint also works on the sites without pretty permalinks
        return f'{self.site_url}/?' + urlencode({
            'wc-auth-version': 1,
            'wc-auth-route': 'authorize',
            'app_name': f'Odoo ({self.company_id.name})',
            'scope': 'read_write',
            'user_id': state,
            'return_url': f'{root}/om_woocommerce/auth/return/{self.id}',
            'callback_url': f'{root}/om_woocommerce/auth/callback',
        })

    @api.model
    def _woo_auth_store_of_state(self, state):
        if not state or not isinstance(state, str):
            return self.browse()
        store = self.sudo().search([('auth_state_hash', '=', hashlib.sha256(state.encode()).hexdigest())], limit=1)
        if store and store.auth_state_expires and store.auth_state_expires >= fields.Datetime.now():
            return store
        return self.browse()

    @api.model
    def _woo_auth_callback(self, data):
        """ The key WooCommerce sends once the administrator approved Odoo. Gives the store. """
        store = self._woo_auth_store_of_state(data.get('user_id'))
        if not store or not data.get('consumer_key') or not data.get('consumer_secret'):
            return self.browse()
        if data.get('key_permissions') not in (None, 'read_write'):
            store.message_post(body=_("WordPress gave a key without the read/write permission: Odoo needs both."))
            return store
        store.write({'consumer_key': data['consumer_key'], 'consumer_secret': data['consumer_secret'],
                     'auth_state_hash': False})
        store.message_post(body=_("WordPress gave Odoo a REST API key (key %(id)s).", id=data.get('key_id') or ''))
        return store

    def _woo_auth_return(self, params):
        """ Back from WordPress: connect with the key it sent, and start the first imports. """
        self.ensure_one()
        store = self.sudo()
        if store.auth_state_uid and store.auth_state_uid.id != self.env.uid:
            raise UserError(_("This authorization was started by another user."))
        if str(params.get('success')) == '0':
            raise UserError(_("The authorization was refused in WordPress."))
        if not store.consumer_key or not store.consumer_secret:
            raise UserError(_("WordPress did not send the key to Odoo. Is the Odoo Public URL reachable from the "
                              "site? Paste a REST API key instead."))
        store.write({'auth_state_expires': False, 'auth_state_uid': False})
        self.action_woo_connect()
        if self.state == 'connected':
            self._woo_start_pending()
        return self

    def _woo_start_pending(self):
        """ The first imports chosen in the setup wizard. """
        self.ensure_one()
        pending = set(filter(None, (self.sudo().setup_pending or '').split(',')))
        self.sudo().setup_pending = False
        if 'products' in pending:
            self.action_woo_import_products()
        if 'customers' in pending:
            self.action_woo_import_customers()
        if 'orders' in pending:
            self.action_woo_import_orders()
        if 'stock' in pending:
            self.action_woo_export_stock()

    def _woo_notification(self, message, kind='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': message, 'type': kind, 'next': {'type': 'ir.actions.act_window_close'}},
        }

    def _woo_ensure_connected(self):
        for store in self:
            if store.state != 'connected':
                raise UserError(_("Connect %(store)s to WooCommerce first.", store=store.name))

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    def _woo_webhook_handlers(self):
        """ ``{topic: (model, method)}``: the webhooks of the store, and the job that processes each
        of them. The method gets the job; ``job.payload`` is the body of the webhook. """
        orders = ('sale.order', '_connector_job_woo_order_webhook')
        products = ('om.woocommerce.product.template', '_connector_job_woo_product_webhook')
        customers = ('om.woocommerce.customer', '_connector_job_woo_customer_webhook')
        return {
            'order.created': orders,
            'order.updated': orders,
            'product.created': products,
            'product.updated': products,
            'product.deleted': ('om.woocommerce.product.template', '_connector_job_woo_product_deleted'),
            'customer.created': customers,
            'customer.updated': customers,
        }

    def _woo_webhooks_possible(self):
        self.ensure_one()
        return bool(self.webhook_url and self.webhook_url.startswith('https://'))

    def action_woo_sync_webhooks(self):
        """ Create the webhooks of the store in WooCommerce, turn on again those WooCommerce disabled
        after failed deliveries, and remove those of Odoo not needed anymore. """
        Webhook = self.env['om.woocommerce.webhook'].sudo()
        for store in self:
            store._woo_ensure_connected()
            if not store._woo_webhooks_possible():
                raise UserError(_("WooCommerce sends webhooks to an https address. Set the Odoo Public URL of "
                                  "%(store)s (for example the address of a tunnel to this Odoo).", store=store.name))
            url = store.webhook_url
            wanted = set(store._woo_webhook_handlers())
            existing = {}
            for hook in store._woo_paginate('webhooks'):
                if hook.get('delivery_url') == url:
                    existing.setdefault(hook['topic'], []).append(hook)
            subscribed = {}
            secret = store.sudo().webhook_secret
            for topic, hooks in existing.items():
                keep = hooks[0] if topic in wanted else None
                for hook in hooks:
                    if hook is not keep:
                        store._woo_delete(f"webhooks/{hook['id']}", {'force': 'true'})
                if keep:
                    # the secret of the store, and active again if WooCommerce disabled it
                    keep = store._woo_put(f"webhooks/{keep['id']}", {'status': 'active', 'secret': secret}) or keep
                    subscribed[topic] = keep
            for topic in sorted(wanted - set(subscribed)):
                subscribed[topic] = store._woo_post('webhooks', {
                    'name': f'Odoo: {topic}', 'topic': topic, 'delivery_url': url, 'secret': secret,
                    'status': 'active',
                }) or {}
            store.webhook_ids.filtered(lambda w: w.topic not in subscribed).unlink()
            known = {w.topic: w for w in store.webhook_ids}
            for topic, hook in subscribed.items():
                vals = {'woo_id': hook.get('id'), 'delivery_url': url, 'status': hook.get('status') or 'active'}
                if topic in known:
                    known[topic].write(vals)
                else:
                    Webhook.create({'store_id': store.id, 'topic': topic, **vals})
        return self._woo_notification(_("Webhooks are up to date."))

    def _woo_receive_webhook(self, topic, payload, delivery_id=None):
        """ Queue the job of a webhook received from WooCommerce; ignore the topics no module handles. """
        self.ensure_one()
        handler = self._woo_webhook_handlers().get(topic)
        if not handler:
            _logger.info("WooCommerce %s: webhook %s ignored, no module handles it", self.site_url, topic)
            return None
        model_name, method_name = handler
        resource, _sep, event = topic.partition('.')
        # a deletion runs another method than a creation or an update: a key of its own
        key = f"{resource}:{payload['id']}" + (':deleted' if event == 'deleted' else '')
        return self._connector_enqueue(
            method_name, payload, model_name=model_name, priority=5,
            name=_("Webhook %(topic)s %(id)s", topic=topic, id=payload.get('id') or ''),
            dedupe_key=key if payload.get('id') else (
                f'webhook:{delivery_id}' if delivery_id else None),
        )

    # ------------------------------------------------------------------
    # Orders: pricelist and taxes
    # ------------------------------------------------------------------

    def _woo_pricelist(self, currency_code):
        return self._connector_pricelist(currency_code, _("WooCommerce"))

    def _woo_taxes(self, rates, included):
        """ The Odoo sale taxes of ``rates`` (``[(percent, label)]``), found or created. """
        return self._connector_taxes(rates, included, self.tax_account_id)

    # ------------------------------------------------------------------
    # Scheduled work
    # ------------------------------------------------------------------

    def _woo_connected(self):
        return self.search([('state', '=', 'connected')])

    @api.model
    def _cron_woo_import_orders(self):
        for store in self._woo_connected().filtered('order_auto_import'):
            store._connector_enqueue_once('_connector_job_woo_fetch_orders', name=_("Look for new orders"))

    @api.model
    def _cron_woo_import_products(self):
        for store in self._woo_connected().filtered('product_auto_import'):
            store._connector_enqueue_once('_connector_job_woo_fetch_products', name=_("Look for changed products"))

    @api.model
    def _cron_woo_export_stock(self):
        for store in self._woo_connected().filtered('stock_export'):
            store._connector_enqueue_once('_connector_job_woo_export_stock', name=_("Send the stock"))

    def _woo_enqueue_export(self, template, images=True):
        self.ensure_one()
        return self._connector_enqueue(
            '_connector_job_woo_export_product', {'template_id': template.id, 'images': images},
            model_name='om.woocommerce.product.template', name=_("Export %(product)s", product=template.name),
            dedupe_key=f'export:{template.id}')

    @api.model
    def _cron_woo_daily(self):
        for store in self._woo_connected().filtered('price_auto_export'):
            store._connector_enqueue_once('_connector_job_woo_export_prices', name=_("Send the prices"))

    def action_woo_export_prices(self):
        self._woo_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_woo_export_prices', name=_("Send the prices"))
        return self._woo_notification(_("The prices are being sent: follow it in Jobs."), kind='info')

    def action_woo_import_orders(self):
        self._woo_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_woo_fetch_orders', name=_("Look for new orders"))
        return self._woo_notification(_("The orders are being imported: follow it in Jobs."), kind='info')

    def action_woo_import_products(self):
        self._woo_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_woo_fetch_products', {'full': True},
                                          name=_("Import all products"))
        return self._woo_notification(_("The products are being imported: follow it in Jobs."), kind='info')

    def action_woo_export_stock(self):
        self._woo_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_woo_export_stock', {'full': True}, name=_("Send all the stock"))
        return self._woo_notification(_("The stock is being sent: follow it in Jobs."), kind='info')

    def action_woo_import_stock(self):
        self._woo_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_woo_import_stock', name=_("Import the stock"))
        return self._woo_notification(_("The stock is being imported: follow it in Jobs."), kind='info')

    def action_woo_import_customers(self):
        self._woo_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_woo_fetch_customers', name=_("Import the customers"))
        return self._woo_notification(_("The customers are being imported: follow it in Jobs."), kind='info')

    @api.model
    def _connector_job_woo_fetch_orders(self, job):
        """ Queue one job per order changed in WooCommerce since the last import: those in a status to
        import, and those imported before. """
        store = job.backend
        started = fields.Datetime.now()
        since = max(filter(None, [
            store.order_import_from,
            store.order_last_sync and store.order_last_sync - timedelta(minutes=10),
        ]), default=started - timedelta(days=7))
        statuses = set(store.order_status_ids.mapped('code'))
        known = set(self.env['sale.order'].search([('woo_store_id', '=', store.id)]).mapped('woo_order_id'))
        count = 0
        for order in store._woo_paginate('orders', {
                'modified_after': self._woo_date(since), 'dates_are_gmt': 'true', 'status': 'any',
                '_fields': 'id,number,status'}):
            if order.get('status') not in statuses and str(order['id']) not in known:
                continue
            store._connector_enqueue('_connector_job_woo_import_order', {'id': order['id']}, model_name='sale.order',
                                     name=_("Order %(number)s", number=order.get('number') or order['id']),
                                     dedupe_key=f"order:{order['id']}")
            count += 1
        store.order_last_sync = started
        return _("%(count)s order(s) to import", count=count)

    @api.model
    def _connector_job_woo_fetch_products(self, job):
        """ Queue one job per product changed in WooCommerce since the last import (all of them the
        first time, or when asked). """
        store = job.backend
        started = fields.Datetime.now()
        params = {'status': 'any', '_fields': 'id,name,type'}
        if store.product_last_sync and not (job.payload or {}).get('full'):
            params.update(modified_after=self._woo_date(store.product_last_sync - timedelta(minutes=10)),
                          dates_are_gmt='true')
        count = 0
        for product in store._woo_paginate('products', params):
            store._connector_enqueue('_connector_job_woo_import_product', {'id': product['id']},
                                     model_name='om.woocommerce.product.template',
                                     name=_("Product %(name)s", name=product.get('name') or product['id']),
                                     dedupe_key=f"product:{product['id']}", priority=20)
            count += 1
        store.product_last_sync = started
        return _("%(count)s product(s) to import", count=count)

    @api.model
    def _connector_job_woo_fetch_customers(self, job):
        store = job.backend
        count = 0
        for customer in store._woo_paginate('customers', {'role': 'all'}):
            store._connector_enqueue('_connector_job_woo_import_customer', {'id': customer['id'], 'data': customer},
                                     model_name='om.woocommerce.customer',
                                     name=_("Customer %(email)s", email=customer.get('email') or customer['id']),
                                     dedupe_key=f"customer:{customer['id']}", priority=30)
            count += 1
        store.customer_last_sync = fields.Datetime.now()
        return _("%(count)s customer(s) to import", count=count)

    @api.model
    def _connector_job_woo_export_stock(self, job):
        """ Send the stock of the warehouse for the linked products: those whose stock moved since the
        last time, or all of them when asked. """
        store = job.backend
        started = fields.Datetime.now()
        variants = self.env['om.woocommerce.product'].search([
            ('store_id', '=', store.id), ('active', '=', True),
            '|', ('product_id.is_storable', '=', True), ('stock_rule', '=', 'fixed'),
        ])
        if store.stock_last_sync and not (job.payload or {}).get('full'):
            moved = self.env['stock.move'].search([
                ('product_id', 'in', variants.product_id.ids),
                ('write_date', '>=', store.stock_last_sync - timedelta(minutes=10)),
            ]).product_id
            variants = variants.filtered(lambda v: v.product_id in moved or v.stock_rule == 'fixed')
        products = variants.product_id.with_context(warehouse_id=store.warehouse_id.id)
        simple, by_parent = [], {}
        for variant in variants:
            quantity = variant._woo_stock_quantity(products.browse(variant.product_id.id)[store.stock_field])
            item = {'id': int(variant.external_id), 'manage_stock': True, 'stock_quantity': quantity}
            if variant.parent_woo_id:
                by_parent.setdefault(variant.parent_woo_id, []).append(item)
            else:
                simple.append(item)
        sent = len(store._woo_batch('products', update=simple)) if simple else 0
        for parent, items in by_parent.items():
            sent += len(store._woo_batch(f'products/{parent}/variations', update=items))
        store.stock_last_sync = started
        return _("%(count)s stock level(s) sent", count=sent)

    @api.model
    def _connector_job_woo_export_prices(self, job):
        """ Send the regular and sale prices of the linked products, by batches. """
        store = job.backend
        started = fields.Datetime.now()
        variants = self.env['om.woocommerce.product'].search([('store_id', '=', store.id), ('active', '=', True)])
        simple, by_parent = [], {}
        for variant in variants:
            item = {'id': int(variant.external_id), **store._woo_prices(variant.product_id)}
            if variant.parent_woo_id:
                by_parent.setdefault(variant.parent_woo_id, []).append(item)
            else:
                simple.append(item)
        sent = len(store._woo_batch('products', update=simple)) if simple else 0
        for parent, items in by_parent.items():
            sent += len(store._woo_batch(f'products/{parent}/variations', update=items))
        store.price_last_sync = started
        return _("%(count)s price(s) sent", count=sent)

    @api.model
    def _connector_job_woo_import_stock(self, job):
        """ Count the stock of WooCommerce in the warehouse of the store. """
        store = job.backend
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        stock_location = store.warehouse_id.lot_stock_id
        variants = self.env['om.woocommerce.product'].search(
            [('store_id', '=', store.id), ('active', '=', True), ('product_id.is_storable', '=', True)])
        by_id = {v.external_id: v for v in variants}
        levels = {}
        for product in store._woo_paginate('products', {'status': 'any',
                                                        '_fields': 'id,type,manage_stock,stock_quantity'}):
            if product.get('type') == 'variable':
                if any(v.parent_woo_id == str(product['id']) for v in variants):
                    for variation in store._woo_paginate(f"products/{product['id']}/variations",
                                                         {'_fields': 'id,manage_stock,stock_quantity'}):
                        if variation.get('manage_stock') is True:
                            levels[str(variation['id'])] = variation.get('stock_quantity') or 0
            elif product.get('manage_stock') is True:
                levels[str(product['id'])] = product.get('stock_quantity') or 0
        quants = Quant.browse()
        for woo_id, available in levels.items():
            variant = by_id.get(woo_id)
            if not variant or variant.product_id.tracking not in (False, 'none'):
                continue
            quant = Quant.search([('product_id', '=', variant.product_id.id),
                                  ('location_id', '=', stock_location.id), ('lot_id', '=', False)], limit=1)
            if quant:
                quant.write({'inventory_quantity': max(available, 0), 'inventory_quantity_set': True})
            else:
                quant = Quant.create({'product_id': variant.product_id.id, 'location_id': stock_location.id,
                                      'inventory_quantity': max(available, 0), 'inventory_quantity_set': True})
            quants |= quant
        if store.stock_import_apply and quants:
            quants.action_apply_inventory()
        return _("%(count)s quantity(ies) imported", count=len(quants))

    def _connector_job_failed(self, job):
        """ An activity for the responsible of the store, once while a failure is not looked at. """
        self.ensure_one()
        self._connector_activity(_("WooCommerce jobs failed"),
                                 _("%(job)s failed: %(error)s", job=job.name, error=(job.error or '')[:300]))

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def action_open_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Products of %(store)s", store=self.name),
            'res_model': 'om.woocommerce.product.template',
            'view_mode': 'list,form',
            'domain': [('store_id', '=', self.id)],
        }

    def action_open_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_woocommerce.om_woocommerce_sale_order_action')
        action['domain'] = [('woo_store_id', '=', self.id)]
        return action

    def action_open_webhooks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Webhooks"),
            'res_model': 'om.woocommerce.webhook',
            'view_mode': 'list',
            'domain': [('store_id', '=', self.id)],
            'context': {'default_store_id': self.id},
        }

    def action_open_site(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'{self.site_url}/wp-admin/', 'target': 'new'}
