import hashlib
import json
import logging
import secrets
import uuid
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL

from odoo.addons.om_connector_base.tools import RetryableJobError, crypto, request_with_retry

from ..tools import queries

from ..tools.client import (
    DEFAULT_API_VERSION,
    DEFAULT_SCOPES,
    ShopifyAuthError,
    ShopifyError,
    ShopifyClient,
    is_valid_shop_domain,
    normalize_shop_domain,
)

_logger = logging.getLogger(__name__)

WEBHOOK_ROUTE = '/om_shopify/webhook/%s'
STOCK_BATCH = 250

SHOP_QUERY = """
query OmShopifyShop {
  shop { id name email myshopifyDomain currencyCode ianaTimezone }
}
"""

WEBHOOKS_QUERY = """
query OmShopifyWebhooks($cursor: String) {
  webhookSubscriptions(first: 100, after: $cursor) {
    nodes { id topic uri }
    pageInfo { hasNextPage endCursor }
  }
}
"""

WEBHOOK_CREATE = """
mutation OmShopifyWebhookCreate($topic: WebhookSubscriptionTopic!, $uri: String!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: {uri: $uri, format: JSON}) {
    webhookSubscription { id topic uri }
    userErrors { field message }
  }
}
"""

WEBHOOK_DELETE = """
mutation OmShopifyWebhookDelete($id: ID!) {
  webhookSubscriptionDelete(id: $id) {
    deletedWebhookSubscriptionId
    userErrors { field message }
  }
}
"""


class OmShopifyStore(models.Model):
    """ A Shopify store connected to Odoo. """
    _name = 'om.shopify.store'
    _description = 'Shopify Store'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'om.connector.backend.mixin']
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    shop_domain = fields.Char(
        string='Store Address', required=True, tracking=True,
        help="The myshopify.com address of the store, for example my-store.myshopify.com.")
    state = fields.Selection([
        ('draft', 'Not Connected'),
        ('connected', 'Connected'),
        ('error', 'Connection Error'),
    ], default='draft', required=True, readonly=True, tracking=True)
    last_error = fields.Text(readonly=True)

    # Credentials
    auth_type = fields.Selection([
        ('client_credentials', 'Client ID and Secret (Dev Dashboard app)'),
        ('oauth', 'Install by Link (OAuth)'),
        ('token', 'Admin API Access Token (custom app)'),
    ], string='Authentication', default='client_credentials', required=True,
        help="Client ID and Secret: an app made in the Shopify Dev Dashboard and installed on a store of its own "
             "organization; Odoo gets a new access token every day by itself.\n"
             "Install by Link (OAuth): the merchant installs the app on the store from Shopify (public apps, or a "
             "store of another organization); Odoo refreshes the token by itself.\n"
             "Admin API Access Token: the token of a custom app made in the admin of the store (shpat_…).")
    oauth_scopes = fields.Char(string='Scopes', default=lambda self: DEFAULT_SCOPES,
                               help="The access scopes asked to the merchant at the installation, separated by commas.")
    oauth_granted_scopes = fields.Char(string='Granted Scopes', readonly=True, copy=False)
    oauth_redirect_url = fields.Char(string='Redirection URL', compute='_compute_oauth_urls',
                                     help="Allowed redirection URL to set in the app, in the Shopify Dev Dashboard.")
    oauth_app_url = fields.Char(string='App URL', compute='_compute_oauth_urls',
                                help="App URL to set in the app: installing from Shopify starts here.")
    refresh_token = fields.Char(groups='om_shopify.group_om_shopify_manager', copy=False,
                                compute='_compute_secrets', inverse='_inverse_refresh_token')
    refresh_token_encrypted = fields.Char(groups='base.group_system', copy=False)
    refresh_token_expires_at = fields.Datetime(string='Refresh Token Valid Until', readonly=True, copy=False,
                                               groups='om_shopify.group_om_shopify_manager')
    oauth_state_hash = fields.Char(groups='base.group_system', copy=False)
    oauth_state_expires = fields.Datetime(groups='base.group_system', copy=False)
    oauth_state_uid = fields.Many2one('res.users', groups='base.group_system', copy=False)
    client_id = fields.Char(string='Client ID', groups='om_shopify.group_om_shopify_manager')
    client_secret = fields.Char(
        string='Client Secret', groups='om_shopify.group_om_shopify_manager',
        compute='_compute_secrets', inverse='_inverse_client_secret',
        help="Also called API secret key. Shopify signs its webhooks with it. Stored encrypted.")
    access_token = fields.Char(string='Access Token', groups='om_shopify.group_om_shopify_manager', copy=False,
                               compute='_compute_secrets', inverse='_inverse_access_token',
                               help="Stored encrypted.")
    client_secret_encrypted = fields.Char(groups='base.group_system', copy=False)
    access_token_encrypted = fields.Char(groups='base.group_system', copy=False)
    secret_key_source = fields.Selection([
        ('server', 'Odoo configuration file'),
        ('database', 'Database secret'),
    ], string='Encryption Key', compute='_compute_secret_key_source',
        help="Where the key that encrypts the secrets comes from. With the database secret, a copy of the database "
             "is enough to read them: set om_connector_key in the Odoo configuration file for a stronger key.")
    token_expires_at = fields.Datetime(groups='om_shopify.group_om_shopify_manager', copy=False, readonly=True)
    api_version = fields.Char(
        string='API Version', required=True, default=DEFAULT_API_VERSION,
        help="Version of the Shopify Admin API. Shopify supports each version for one year.")

    # Store details, read from Shopify
    shop_gid = fields.Char(string='Shopify ID', readonly=True, copy=False)
    shop_name = fields.Char(readonly=True, copy=False)
    shop_email = fields.Char(readonly=True, copy=False)
    shop_currency_id = fields.Many2one('res.currency', string='Store Currency', readonly=True, copy=False)
    shop_timezone = fields.Char(string='Store Timezone', readonly=True, copy=False)

    # Webhooks
    webhook_base_url = fields.Char(
        string='Odoo Public URL',
        help="Public https address of this Odoo, where Shopify sends its webhooks. Empty: the web.base.url of Odoo.")
    webhook_url = fields.Char(string='Webhook Address', compute='_compute_webhook_url')
    webhook_ids = fields.One2many('om.shopify.webhook', 'store_id', string='Webhooks')
    webhook_count = fields.Integer(compute='_compute_webhook_count')

    # Odoo side
    warehouse_id = fields.Many2one('stock.warehouse', required=True, check_company=True,
                                   default=lambda self: self._default_warehouse(),
                                   help="Warehouse of the imported orders.")
    team_id = fields.Many2one('crm.team', string='Sales Team', check_company=True)
    user_id = fields.Many2one('res.users', string='Salesperson', domain="[('share', '=', False)]")
    location_ids = fields.One2many('om.shopify.location', 'store_id', string='Locations')
    gateway_ids = fields.One2many('om.shopify.gateway', 'store_id', string='Payment Methods')

    # Products
    product_match = fields.Selection([
        ('sku', 'SKU (Internal Reference)'),
        ('barcode', 'Barcode'),
        ('sku_barcode', 'SKU, then Barcode'),
    ], string='Match Products On', default='sku_barcode', required=True,
        help="How a Shopify variant finds its Odoo product the first time.")
    product_auto_create = fields.Boolean(string='Create Missing Products', default=True,
                                         help="Creates the Odoo product of a Shopify variant that matches none.")
    product_import_images = fields.Boolean(string='Import Images', default=True,
                                           help="Gives the image of the Shopify product to an Odoo product without one.")
    product_auto_import = fields.Boolean(string='Import Products Every Day', default=True)
    product_bulk_import = fields.Boolean(
        string='Bulk Import', default=True,
        help="Import All Products asks Shopify for the whole catalogue in one file (bulk operation), much faster "
             "for large catalogues than page after page.")
    product_last_sync = fields.Datetime(string='Products Imported On', readonly=True, copy=False)
    product_count = fields.Integer(compute='_compute_counts', string='Products')

    # Orders
    order_auto_import = fields.Boolean(string='Import Orders Automatically', default=True,
                                       help="Imports the new and updated orders every 15 minutes, besides the webhooks.")
    order_import_from = fields.Datetime(
        string='Import Orders From', default=lambda self: fields.Datetime.now(),
        help="Orders updated before this date are not imported. Orders older than 60 days need the read_all_orders "
             "scope.")
    order_last_sync = fields.Datetime(string='Orders Imported On', readonly=True, copy=False)
    order_import_test = fields.Boolean(string='Import Test Orders', default=True,
                                       help="Imports the orders paid with the test gateways of Shopify.")
    order_use_shopify_name = fields.Boolean(string='Use the Shopify Order Number',
                                            help="Names the sale orders like in Shopify (#1001), instead of the Odoo sequence.")
    order_prefix = fields.Char(string='Order Prefix', help="Put before the Shopify order number, e.g. SH.")
    workflow_id = fields.Many2one('om.connector.order.workflow', string='Default Workflow', check_company=True,
                                  help="Workflow of the orders of a new payment method.")
    tax_mode = fields.Selection([
        ('shopify', 'Taxes of Shopify'),
        ('odoo', 'Taxes of Odoo'),
    ], string='Order Taxes', default='shopify', required=True,
        help="Taxes of Shopify: each line gets an Odoo tax of the rate charged by Shopify, found or created.\n"
             "Taxes of Odoo: each line gets the taxes of its product and the fiscal position of the customer.")
    shipping_product_id = fields.Many2one('product.product', string='Shipping Product', required=True,
                                          default=lambda self: self.env.ref('om_shopify.product_shopify_shipping', False))
    tip_product_id = fields.Many2one('product.product', string='Tip Product', required=True,
                                     default=lambda self: self.env.ref('om_shopify.product_shopify_tip', False))
    gift_card_product_id = fields.Many2one('product.product', string='Gift Card Product', required=True,
                                           default=lambda self: self.env.ref('om_shopify.product_shopify_gift_card', False))
    custom_product_id = fields.Many2one('product.product', string='Custom Item Product', required=True,
                                        default=lambda self: self.env.ref('om_shopify.product_shopify_custom', False),
                                        help="Product of the order lines without a product in Shopify.")
    order_count = fields.Integer(compute='_compute_counts', string='Orders')
    order_rule_ids = fields.One2many('om.shopify.order.rule', 'store_id', string='Order Rules')
    order_currency = fields.Selection([
        ('shop', 'Store Currency'),
        ('customer', 'Currency of the Customer'),
    ], string='Order Currency', default='shop', required=True,
        help="Store Currency: the orders are in the currency of the store.\n"
             "Currency of the Customer: the orders are in the currency the customer paid in (Shopify Markets).")
    order_warehouse_from_location = fields.Boolean(
        string='Warehouse of the Shopify Location',
        help="An order gets the warehouse of the Shopify location that fulfills it, when it has one.")
    order_deliver_fulfilled = fields.Boolean(
        string='Deliver Fulfilled Orders', default=True,
        help="An order already fulfilled in Shopify when imported has its delivery done in Odoo.")
    order_sync_edits = fields.Boolean(
        string='Apply Order Edits', default=True,
        help="Lines added, removed or changed in Shopify are applied to the sale order, while it is neither "
             "delivered nor invoiced.")
    order_import_pos = fields.Boolean(string='Import Point of Sale Orders', default=True)
    pos_partner_id = fields.Many2one('res.partner', string='Point of Sale Customer',
                                     help="Customer of the point of sale orders without a customer.")
    duties_product_id = fields.Many2one('product.product', string='Duties Product', required=True,
                                        default=lambda self: self.env.ref('om_shopify.product_shopify_duties', False))
    refund_adjustment_product_id = fields.Many2one(
        'product.product', string='Refund Adjustment Product', required=True,
        default=lambda self: self.env.ref('om_shopify.product_shopify_refund_adjustment', False))
    tax_account_id = fields.Many2one('account.account', string='Account of the New Taxes', check_company=True,
                                     help="Account of the taxes that Odoo creates for the Shopify rates.")
    gdpr_anonymize = fields.Boolean(
        string='Anonymize Redacted Customers',
        help="When Shopify asks to erase a customer (GDPR), the contact is anonymized and archived. Unticked: the "
             "responsible gets an activity to decide, as invoices may have to be kept.")
    responsible_id = fields.Many2one('res.users', string='Responsible', domain="[('share', '=', False)]",
                                     help="Gets an activity when a job fails or an order is risky.")

    # Refunds
    refund_import = fields.Boolean(string='Import Refunds', default=True,
                                   help="A refund made in Shopify becomes a credit note, paid back in the journal of "
                                        "the payment method.")
    refund_create_return = fields.Boolean(string='Return Restocked Products',
                                          help="Products restocked by a Shopify refund are returned in Odoo.")
    refund_validate_return = fields.Boolean(string='Validate the Return')
    refund_restock_type = fields.Selection([
        ('NO_RESTOCK', 'No Restock'),
        ('RETURN', 'Return to Stock'),
        ('CANCEL', 'Cancel (not shipped yet)'),
    ], string='Restock of Odoo Refunds', default='NO_RESTOCK', required=True,
        help="What Shopify does with the stock of the products of a credit note refunded from Odoo.")
    refund_notify = fields.Boolean(string='Email the Refunds to the Customer')

    # Product export and prices
    product_export_status = fields.Selection([
        ('ACTIVE', 'Active'), ('DRAFT', 'Draft'), ('UNLISTED', 'Unlisted'),
    ], string='Status of Exported Products', default='DRAFT', required=True)
    product_publish = fields.Boolean(string='Publish on the Online Store',
                                     help="Exported products are published on the Online Store sales channel "
                                          "(scope write_publications).")
    price_pricelist_id = fields.Many2one('product.pricelist', string='Price List', check_company=True,
                                         help="Prices sent to Shopify. Empty: the sales price of the products.")
    compare_pricelist_id = fields.Many2one('product.pricelist', string='Compare-at Price List', check_company=True,
                                           help="Compare-at prices sent to Shopify, when higher than the price.")
    price_auto_export = fields.Boolean(string='Send Prices Every Day',
                                       help="Sends the prices of the linked products to Shopify every day.")

    # Stock import, customers, payouts
    stock_import_apply = fields.Boolean(string='Apply the Imported Stock',
                                        help="Applies the quantities imported from Shopify at once, instead of "
                                             "leaving them to count in the physical inventory.")
    customer_last_sync = fields.Datetime(string='Customers Imported On', readonly=True, copy=False)
    payout_import = fields.Boolean(string='Import Payouts',
                                   help="Imports the payouts of Shopify Payments every day as bank statement lines.")
    payout_journal_id = fields.Many2one('account.journal', string='Payout Journal', check_company=True,
                                        domain="[('type', '=', 'bank')]")
    payout_last_sync = fields.Datetime(string='Payouts Imported On', readonly=True, copy=False)
    payout_mode = fields.Selection([
        ('statement', 'Bank statement lines'),
        ('entry', 'Journal entry through a transit account'),
    ], string='Payouts As', default='statement', required=True,
        help="Journal entry: the payments of Shopify Payments wait on a transit account; each payout is one entry "
             "that clears them, books the fees, and is matched with the bank transaction.\n"
             "Bank statement lines: each charge, refund and the fees become lines of the payout journal, to "
             "reconcile by hand.")
    payout_transit_account_id = fields.Many2one(
        'account.account', string='Transit Account', check_company=True,
        help="Where the payments of Shopify Payments wait until their payout. Use it as the outstanding account of "
             "the journal of these payments.")
    payout_fee_account_id = fields.Many2one('account.account', string='Fee Account', check_company=True)
    payout_adjustment_account_id = fields.Many2one('account.account', string='Adjustment Account', check_company=True,
                                                   help="Chargebacks, reserves and other adjustments of the payouts.")
    payout_clearing_account_id = fields.Many2one(
        'account.account', string='Clearing Account', check_company=True,
        help="The net amount of a payout waits here until the bank transaction clears it: the internal transfer "
             "account by default.")
    payout_entry_journal_id = fields.Many2one('account.journal', string='Payout Entries Journal', check_company=True,
                                              domain="[('type', '=', 'general')]")
    payout_ids = fields.One2many('om.shopify.payout', 'store_id', string='Payouts')

    # Stock and fulfillment
    stock_export = fields.Boolean(string='Send Stock to Shopify', default=True,
                                  help="Sends the stock of the warehouses of the locations every 15 minutes.")
    stock_field = fields.Selection([
        ('free_qty', 'Free to Use (on hand minus reserved)'),
        ('qty_available', 'On Hand'),
        ('virtual_available', 'Forecasted'),
    ], string='Stock Sent', default='free_qty', required=True)
    stock_last_sync = fields.Datetime(string='Stock Sent On', readonly=True, copy=False)
    fulfillment_push = fields.Boolean(string='Fulfill in Shopify', default=True,
                                      help="When a delivery of a Shopify order is done, fulfills it in Shopify with the "
                                           "tracking number.")
    fulfillment_notify = fields.Boolean(string='Email the Customer', default=True,
                                        help="Shopify emails the shipping confirmation to the customer.")

    _shop_domain_company_unique = models.Constraint(
        'unique (shop_domain, company_id)', "This store is already connected in this company.")

    @api.model
    def _default_warehouse(self):
        return self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)

    def _compute_counts(self):
        products = dict(self.env['om.shopify.product.template']._read_group(
            [('store_id', 'in', self.ids)], ['store_id'], ['__count']))
        orders = dict(self.env['sale.order']._read_group(
            [('shopify_store_id', 'in', self.ids)], ['shopify_store_id'], ['__count']))
        for store in self:
            store.product_count = products.get(store, 0)
            store.order_count = orders.get(store, 0)

    @api.depends('client_secret_encrypted', 'access_token_encrypted', 'refresh_token_encrypted')
    def _compute_secrets(self):
        for store in self:
            sudo = store.sudo()
            store.client_secret = crypto.decrypt(self.env, sudo.client_secret_encrypted)
            store.access_token = crypto.decrypt(self.env, sudo.access_token_encrypted)
            store.refresh_token = crypto.decrypt(self.env, sudo.refresh_token_encrypted)

    def _inverse_refresh_token(self):
        for store in self:
            store.sudo().refresh_token_encrypted = crypto.encrypt(self.env, store.refresh_token)

    @api.depends('webhook_base_url')
    def _compute_oauth_urls(self):
        base_url = self.get_base_url()
        for store in self:
            root = (store.webhook_base_url or base_url).rstrip('/')
            store.oauth_redirect_url = f'{root}/om_shopify/oauth/callback'
            store.oauth_app_url = f'{root}/om_shopify/oauth/install'

    def _inverse_client_secret(self):
        for store in self:
            store.sudo().client_secret_encrypted = crypto.encrypt(self.env, store.client_secret)

    def _inverse_access_token(self):
        for store in self:
            store.sudo().access_token_encrypted = crypto.encrypt(self.env, store.access_token)

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

    @api.onchange('shop_domain')
    def _onchange_shop_domain(self):
        if self.shop_domain:
            self.shop_domain = normalize_shop_domain(self.shop_domain)
            if not self.name:
                self.name = self.shop_domain.split('.')[0].replace('-', ' ').title()

    @api.constrains('shop_domain')
    def _check_shop_domain(self):
        for store in self:
            if not is_valid_shop_domain(store.shop_domain):
                raise ValidationError(_("%(domain)s is not a store address: it looks like my-store.myshopify.com.",
                                        domain=store.shop_domain))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('shop_domain'):
                vals['shop_domain'] = normalize_shop_domain(vals['shop_domain'])
        stores = super().create(vals_list)
        for store in stores.filtered(lambda s: not s.workflow_id):
            store.workflow_id = store._shopify_default_workflow()
        return stores

    def _shopify_default_workflow(self):
        self.ensure_one()
        journal = self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.company_id.id)], limit=1)
        return self.env['om.connector.order.workflow'].sudo().create({
            'name': _("%(store)s: paid orders", store=self.name),
            'company_id': self.company_id.id,
            'journal_id': journal.id,
            'register_payment': bool(journal),
        })

    def write(self, vals):
        if vals.get('shop_domain'):
            vals['shop_domain'] = normalize_shop_domain(vals['shop_domain'])
        res = super().write(vals)
        if {'shop_domain', 'auth_type', 'client_id', 'client_secret'} & set(vals):
            # a token of other credentials is not used anymore
            self.sudo().filtered(lambda s: s.auth_type == 'client_credentials').write(
                {'access_token': False, 'token_expires_at': False})
        return res

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def _shopify_token(self, refresh=False):
        """ The access token, a new one when it is expired (client ID and secret, OAuth). """
        self.ensure_one()
        store = self.sudo()
        if store.auth_type == 'oauth':
            if not store.access_token:
                raise UserError(_("Click Connect with Shopify on %(store)s to install the app.", store=store.name))
            expired = store.token_expires_at and store.token_expires_at <= fields.Datetime.now() + timedelta(minutes=2)
            if store.refresh_token and (refresh or expired):
                self._shopify_refresh_oauth(force=refresh)
                store.invalidate_recordset(['access_token', 'access_token_encrypted', 'token_expires_at'])
            return store.access_token
        if store.auth_type == 'token':
            if not store.access_token:
                raise UserError(_("Set the access token of %(store)s.", store=store.name))
            return store.access_token
        if not store.client_id or not store.client_secret:
            raise UserError(_("Set the client ID and secret of %(store)s.", store=store.name))
        now = fields.Datetime.now()
        if refresh or not store.access_token or not store.token_expires_at or store.token_expires_at <= now:
            token, seconds = ShopifyClient.fetch_client_credentials_token(
                store.shop_domain, store.client_id, store.client_secret)
            # renewed one hour before it expires
            store.write({'access_token': token,
                         'token_expires_at': now + timedelta(seconds=max(seconds - 3600, 60))})
        return store.access_token

    def _shopify_oauth_token_vals(self, data):
        """ The values of a store from the token answer of Shopify. """
        now = fields.Datetime.now()
        vals = {'access_token': data['access_token'],
                'token_expires_at': now + timedelta(seconds=int(data['expires_in'])) if data.get('expires_in') else False}
        if data.get('refresh_token'):
            vals['refresh_token'] = data['refresh_token']
            vals['refresh_token_expires_at'] = now + timedelta(seconds=int(data.get('refresh_token_expires_in') or 0)) \
                if data.get('refresh_token_expires_in') else False
        if data.get('scope'):
            vals['oauth_granted_scopes'] = data['scope']
        return vals

    def _shopify_refresh_oauth(self, force=False):
        """ Get a new access token with the refresh token. Shopify gives a new refresh token and
        retires the old one at once: both are saved in a transaction of their own, under a lock, so that
        a rollback of the current work, or another worker refreshing at the same time, never loses them. """
        self.ensure_one()
        refused = None
        with self.env.registry.cursor() as cr:
            env = self.env(cr=cr, su=True)
            cr.execute(SQL("SELECT id FROM om_shopify_store WHERE id = %s FOR UPDATE", self.id))
            store = env['om.shopify.store'].browse(self.id)
            soon = fields.Datetime.now() + timedelta(minutes=2)
            if not force and store.token_expires_at and store.token_expires_at > soon:
                return  # refreshed by another worker meanwhile
            try:
                data = ShopifyClient.refresh_oauth_token(store.shop_domain, store.client_id, store.client_secret,
                                                         store.refresh_token)
            except ShopifyAuthError as e:
                refused = e
                store.write({'state': 'error', 'last_error': _("%(error)s Click Connect with Shopify again.", error=e)})
            else:
                store.write(self._shopify_oauth_token_vals(data))
            cr.commit()
        self.invalidate_recordset(['state', 'last_error'])
        if refused:
            raise refused

    def action_shopify_oauth_start(self):
        self.ensure_one()
        if self.auth_type != 'oauth':
            raise UserError(_("This store does not use the installation by link."))
        if not self.sudo().client_id or not self.sudo().client_secret:
            raise UserError(_("Set the client ID and secret of the app first."))
        return {'type': 'ir.actions.act_url', 'url': f'/om_shopify/oauth/start/{self.id}', 'target': 'self'}

    def _shopify_oauth_authorize_url(self):
        """ A new state for this installation, and the page of Shopify where the merchant approves it. """
        self.ensure_one()
        state = secrets.token_urlsafe(32)
        self.sudo().write({
            'oauth_state_hash': hashlib.sha256(state.encode()).hexdigest(),
            'oauth_state_expires': fields.Datetime.now() + timedelta(minutes=15),
            'oauth_state_uid': self.env.uid,
        })
        scopes = ','.join(scope.strip() for scope in (self.oauth_scopes or DEFAULT_SCOPES).split(',') if scope.strip())
        return ShopifyClient.authorize_url(self.shop_domain, self.sudo().client_id, scopes, self.oauth_redirect_url,
                                           state)

    @api.model
    def _shopify_oauth_store_of_state(self, state):
        if not state:
            return self.browse()
        return self.sudo().search([('oauth_state_hash', '=', hashlib.sha256(state.encode()).hexdigest()),
                                   ('auth_type', '=', 'oauth')], limit=1)

    def _shopify_oauth_complete(self, params):
        """ Check the callback of Shopify (signature, state, store) and exchange its code for the tokens. """
        self.ensure_one()
        store = self.sudo()
        if not store.oauth_state_expires or store.oauth_state_expires < fields.Datetime.now():
            raise UserError(_("The installation expired: click Connect with Shopify again."))
        if store.oauth_state_uid.id != self.env.uid:
            raise UserError(_("The installation was started by another user."))
        if normalize_shop_domain(params.get('shop')) != store.shop_domain or not is_valid_shop_domain(params.get('shop')):
            raise UserError(_("Shopify answered for another store."))
        if not ShopifyClient.verify_oauth_query(store.client_secret, params):
            raise UserError(_("The answer of Shopify is not signed by the app."))
        data = ShopifyClient.fetch_oauth_token(store.shop_domain, store.client_id, store.client_secret,
                                               params.get('code'))
        store.write({**self._shopify_oauth_token_vals(data), 'oauth_state_hash': False, 'oauth_state_expires': False,
                     'oauth_state_uid': False})
        return self.action_shopify_connect()

    def _shopify_client(self, refresh=False):
        self.ensure_one()
        return ShopifyClient(self.shop_domain, self._shopify_token(refresh=refresh), self.api_version)

    def _shopify_call(self, method, *args, **kwargs):
        """ ``ShopifyClient.<method>(*args)``, with a new token and a second try when the token of
        an app of the Dev Dashboard was refused. """
        self.ensure_one()
        try:
            return getattr(self._shopify_client(), method)(*args, **kwargs)
        except ShopifyAuthError:
            if self.sudo().auth_type == 'token' or (self.sudo().auth_type == 'oauth' and not self.sudo().refresh_token):
                raise
            return getattr(self._shopify_client(refresh=True), method)(*args, **kwargs)

    def _shopify_execute(self, query, variables=None):
        return self._shopify_call('execute', query, variables)

    def _shopify_mutate(self, query, variables, field, errors_key='userErrors'):
        return self._shopify_call('mutate', query, variables, field, errors_key)

    def _shopify_paginate(self, query, variables, path):
        """ Every node of a connection. A generator: the token is checked before the first page. """
        self.ensure_one()
        client = self._shopify_client()
        try:
            iterator = client.paginate(query, variables, path)
            first = next(iterator, None)
        except ShopifyAuthError:
            if self.sudo().auth_type == 'token' or (self.sudo().auth_type == 'oauth' and not self.sudo().refresh_token):
                raise
            client = self._shopify_client(refresh=True)
            iterator = client.paginate(query, variables, path)
            first = next(iterator, None)
        if first is None:
            return
        yield first
        yield from iterator

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def action_shopify_connect(self):
        """ Check the credentials, read the details of the store and subscribe to the webhooks. """
        for store in self:
            try:
                shop = store._shopify_execute(SHOP_QUERY).get('shop') or {}
            except UserError as e:
                # not raised: the error is kept on the store
                store.write({'state': 'error', 'last_error': str(e)})
                return self._shopify_notification(str(e), kind='danger')
            currency = self.env['res.currency'].with_context(active_test=False).search(
                [('name', '=', shop.get('currencyCode'))], limit=1)
            store.write({
                'state': 'connected',
                'last_error': False,
                'shop_gid': shop.get('id'),
                'shop_name': shop.get('name'),
                'shop_email': shop.get('email'),
                'shop_timezone': shop.get('ianaTimezone'),
                'shop_currency_id': currency.id,
            })
            store.message_post(body=_("Connected to %(shop)s.", shop=shop.get('name') or store.shop_domain))
            self.env['om.shopify.location']._shopify_import(store)
            if store._shopify_webhook_handlers():
                if store._shopify_webhooks_possible():
                    store.action_shopify_sync_webhooks()
                else:
                    store.message_post(body=_(
                        "No webhooks: Shopify sends them to an https address only, and %(url)s is not one. Set the "
                        "Odoo Public URL of the store, then click Sync Webhooks. The scheduled imports still run.",
                        url=store.webhook_url))
        return self._shopify_notification(_("Connected to Shopify."))

    def _shopify_notification(self, message, kind='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': message, 'type': kind, 'next': {'type': 'ir.actions.act_window_close'}},
        }

    def _shopify_ensure_connected(self):
        for store in self:
            if store.state != 'connected':
                raise UserError(_("Connect %(store)s to Shopify first.", store=store.name))

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    def _shopify_webhook_handlers(self):
        """ ``{topic: (model, method)}``: the webhooks of the store, and the job that processes each
        of them. The method gets the job; ``job.payload`` is the body of the webhook. Each module
        adds its topics (``ORDERS_CREATE``, ``PRODUCTS_UPDATE``…). """
        orders = ('sale.order', '_connector_job_shopify_order_webhook')
        customers = ('om.shopify.customer', '_connector_job_shopify_customer_webhook')
        return {
            'REFUNDS_CREATE': ('sale.order', '_connector_job_shopify_refund_webhook'),
            'CUSTOMERS_CREATE': customers,
            'CUSTOMERS_UPDATE': customers,
            'APP_UNINSTALLED': ('om.shopify.store', '_connector_job_shopify_app_uninstalled'),
            'PRODUCTS_CREATE': ('om.shopify.product.template', '_connector_job_shopify_product_webhook'),
            'PRODUCTS_UPDATE': ('om.shopify.product.template', '_connector_job_shopify_product_webhook'),
            'PRODUCTS_DELETE': ('om.shopify.product.template', '_connector_job_shopify_product_deleted'),
            'ORDERS_CREATE': orders,
            'ORDERS_UPDATED': orders,
            'ORDERS_CANCELLED': orders,
        }

    def _shopify_webhooks_possible(self):
        self.ensure_one()
        return bool(self.webhook_url and self.webhook_url.startswith('https://'))

    def action_shopify_sync_webhooks(self):
        """ Subscribe to the webhooks of the store, and remove the subscriptions of Odoo that are not
        needed anymore. """
        Webhook = self.env['om.shopify.webhook'].sudo()
        for store in self:
            store._shopify_ensure_connected()
            if not store._shopify_webhooks_possible():
                raise UserError(_("Shopify sends webhooks to an https address only. Set the Odoo Public URL of "
                                  "%(store)s (for example the address of a tunnel to this Odoo).", store=store.name))
            uri = store.webhook_url
            wanted = set(store._shopify_webhook_handlers())
            existing = {}
            for node in store._shopify_paginate(WEBHOOKS_QUERY, {}, 'webhookSubscriptions'):
                if node.get('uri') == uri:
                    existing.setdefault(node['topic'], []).append(node['id'])
            for topic, gids in existing.items():
                # duplicates and topics no module handles anymore
                for gid in (gids[1:] if topic in wanted else gids):
                    store._shopify_mutate(WEBHOOK_DELETE, {'id': gid}, 'webhookSubscriptionDelete')
            subscribed = {topic: gids[0] for topic, gids in existing.items() if topic in wanted}
            for topic in sorted(wanted - set(subscribed)):
                result = store._shopify_mutate(WEBHOOK_CREATE, {'topic': topic, 'uri': uri},
                                               'webhookSubscriptionCreate')
                subscribed[topic] = (result.get('webhookSubscription') or {}).get('id')
            store.webhook_ids.filtered(lambda w: w.topic not in subscribed).unlink()
            known = {w.topic: w for w in store.webhook_ids}
            for topic, gid in subscribed.items():
                vals = {'shopify_gid': gid, 'uri': uri}
                if topic in known:
                    known[topic].write(vals)
                else:
                    Webhook.create({'store_id': store.id, 'topic': topic, **vals})
        return self._shopify_notification(_("Webhooks are up to date."))

    def _shopify_compliance_handlers(self):
        """ The privacy (GDPR) webhooks: Shopify sends them to the compliance address set in the app,
        they are not subscribed by Odoo. """
        return {
            'CUSTOMERS_DATA_REQUEST': ('om.shopify.store', '_connector_job_shopify_gdpr_data_request'),
            'CUSTOMERS_REDACT': ('om.shopify.store', '_connector_job_shopify_gdpr_customer_redact'),
            'SHOP_REDACT': ('om.shopify.store', '_connector_job_shopify_gdpr_shop_redact'),
        }

    def _shopify_receive_webhook(self, topic, payload, webhook_id=None):
        """ Queue the job of a webhook received from Shopify; ignore the topics no module handles. """
        self.ensure_one()
        handler = {**self._shopify_webhook_handlers(), **self._shopify_compliance_handlers()}.get(topic)
        if not handler:
            _logger.info("Shopify %s: webhook %s ignored, no module handles it", self.shop_domain, topic)
            return None
        model_name, method_name = handler
        return self._connector_enqueue(
            method_name, payload, model_name=model_name, priority=5,
            name=_("Webhook %(topic)s", topic=topic.replace('_', ' ').lower()),
            dedupe_key=f'webhook:{webhook_id}' if webhook_id else None,
        )

    @api.model
    def _connector_job_shopify_app_uninstalled(self, job):
        store = job.backend
        store.sudo().write({'state': 'error', 'access_token': False, 'token_expires_at': False,
                            'last_error': _("The app was uninstalled from the store.")})
        store.webhook_ids.sudo().unlink()
        store.message_post(body=_("The app was uninstalled from the Shopify store: Odoo cannot reach it anymore."))
        return store

    # ------------------------------------------------------------------
    # Orders: pricelist and taxes
    # ------------------------------------------------------------------

    def _shopify_pricelist(self, currency_code):
        """ A pricelist in the currency of the order, when it is not the currency of the company. """
        return self._connector_pricelist(currency_code, _("Shopify"))

    def _shopify_taxes(self, tax_lines, taxes_included):
        """ The Odoo sale taxes of the rates of ``tax_lines``, found or created. """
        rates = [(float(line.get('rate') or 0.0) * 100.0, line.get('title')) for line in tax_lines or []]
        return self._connector_taxes(rates, taxes_included, self.tax_account_id)

    # ------------------------------------------------------------------
    # Scheduled work
    # ------------------------------------------------------------------

    def _shopify_connected(self):
        return self.search([('state', '=', 'connected')])

    @api.model
    def _cron_shopify_import_orders(self):
        for store in self._shopify_connected().filtered('order_auto_import'):
            store._connector_enqueue_once('_connector_job_shopify_fetch_orders', name=_("Look for new orders"))

    @api.model
    def _cron_shopify_import_products(self):
        for store in self._shopify_connected().filtered('product_auto_import'):
            store._connector_enqueue_once('_connector_job_shopify_fetch_products', name=_("Look for changed products"))

    @api.model
    def _cron_shopify_export_stock(self):
        for store in self._shopify_connected().filtered('stock_export'):
            store._connector_enqueue_once('_connector_job_shopify_export_stock', name=_("Send the stock"))

    def action_shopify_import_orders(self):
        self._shopify_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_shopify_fetch_orders', name=_("Look for new orders"))
        return self._shopify_notification(_("The orders are being imported: follow it in Jobs."), kind='info')

    def action_shopify_import_products(self):
        self._shopify_ensure_connected()
        for store in self:
            if store.product_bulk_import:
                store._connector_enqueue_once('_connector_job_shopify_bulk_products', name=_("Import all products (bulk)"))
            else:
                store._connector_enqueue_once('_connector_job_shopify_fetch_products', {'full': True},
                                              name=_("Import all products"))
        return self._shopify_notification(_("The products are being imported: follow it in Jobs."), kind='info')

    def action_shopify_export_stock(self):
        self._shopify_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_shopify_export_stock', {'full': True},
                                          name=_("Send all the stock"))
        return self._shopify_notification(_("The stock is being sent: follow it in Jobs."), kind='info')

    def action_shopify_import_locations(self):
        self._shopify_ensure_connected()
        for store in self:
            self.env['om.shopify.location']._shopify_import(store)
        return self._shopify_notification(_("Locations imported."))

    @staticmethod
    def _shopify_search_date(value):
        return fields.Datetime.to_datetime(value).strftime('%Y-%m-%dT%H:%M:%SZ')

    @api.model
    def _connector_job_shopify_fetch_orders(self, job):
        """ Queue one job per order updated in Shopify since the last import. """
        store = job.backend
        started = fields.Datetime.now()
        since = max(filter(None, [
            store.order_import_from,
            store.order_last_sync and store.order_last_sync - timedelta(minutes=10),
        ]), default=started - timedelta(days=7))
        search = f"updated_at:>='{self._shopify_search_date(since)}'"
        count = 0
        for node in store._shopify_paginate(queries.ORDER_IDS, {'query': search}, 'orders'):
            store._connector_enqueue('_connector_job_shopify_import_order', {'id': node['id'],
                                                                             'updatedAt': node['updatedAt']},
                                     model_name='sale.order', name=_("Order %(name)s", name=node['name']),
                                     dedupe_key=f"order:{node['id']}")
            count += 1
        store.order_last_sync = started
        return _("%(count)s order(s) to import", count=count)

    @api.model
    def _connector_job_shopify_fetch_products(self, job):
        """ Queue one job per product changed in Shopify since the last import (all of them the
        first time, or when asked). """
        store = job.backend
        started = fields.Datetime.now()
        search = None
        if store.product_last_sync and not (job.payload or {}).get('full'):
            search = f"updated_at:>='{self._shopify_search_date(store.product_last_sync - timedelta(minutes=10))}'"
        count = 0
        for node in store._shopify_paginate(queries.PRODUCT_IDS, {'query': search}, 'products'):
            store._connector_enqueue('_connector_job_shopify_import_product', {'id': node['id'],
                                                                               'updatedAt': node['updatedAt']},
                                     model_name='om.shopify.product.template',
                                     name=_("Product %(id)s", id=node['id'].rsplit('/', 1)[-1]),
                                     dedupe_key=f"product:{node['id']}", priority=20)
            count += 1
        store.product_last_sync = started
        return _("%(count)s product(s) to import", count=count)

    @api.model
    def _connector_job_shopify_bulk_products(self, job):
        """ Start a bulk operation exporting the whole catalogue; a job waits for its file. """
        store = job.backend
        result = store._shopify_mutate(queries.BULK_RUN, {'query': store._shopify_query(queries.BULK_PRODUCTS, bulk=True)},
                                       'bulkOperationRunQuery')
        operation = result.get('bulkOperation') or {}
        store.product_last_sync = fields.Datetime.now()
        store._connector_enqueue('_connector_job_shopify_bulk_poll', {'id': operation['id'], 'kind': 'products'},
                                 name=_("Wait for the catalogue of Shopify"), max_attempts=240,
                                 eta=fields.Datetime.now() + timedelta(seconds=15),
                                 dedupe_key=f"bulk:{operation['id']}")
        return _("Bulk operation %(id)s started", id=operation['id'])

    @api.model
    def _connector_job_shopify_bulk_poll(self, job):
        """ Wait for the bulk operation, then queue one job per product of its file. """
        store = job.backend
        operation = store._shopify_execute(queries.BULK_STATUS, {'id': job.payload['id']}).get('bulkOperation') or {}
        status = operation.get('status')
        if status in ('CREATED', 'RUNNING', 'CANCELING'):
            raise RetryableJobError(_("Shopify prepares the file: %(count)s object(s) so far",
                                      count=operation.get('objectCount') or 0), delay=30)
        if status != 'COMPLETED':
            raise UserError(_("The bulk operation of Shopify ended as %(status)s (%(error)s).",
                              status=status, error=operation.get('errorCode') or _("no error code")))
        if not operation.get('url'):
            return _("The catalogue of Shopify is empty")
        count = 0
        for product in self._shopify_bulk_products(operation['url']):
            store._connector_enqueue('_connector_job_shopify_import_product',
                                     {'id': product['id'], 'updatedAt': product.get('updatedAt'), 'data': product},
                                     model_name='om.shopify.product.template',
                                     name=_("Product %(name)s", name=product.get('title') or product['id']),
                                     dedupe_key=f"product:{product['id']}", priority=20)
            count += 1
        return _("%(count)s product(s) to import", count=count)

    @api.model
    def _shopify_bulk_products(self, url):
        """ The products of the JSONL file of a bulk operation, each with its variants. Lines of a
        product come before the lines of its variants, which give it as ``__parentId``. """
        response = request_with_retry('GET', url, timeout=300, stream=True)
        if response.status_code >= 400:
            raise ShopifyError(f"The file of the bulk operation cannot be downloaded (HTTP {response.status_code}).")
        current = None
        for raw in response.iter_lines():
            if not raw:
                continue
            node = json.loads(raw)
            parent = node.pop('__parentId', None)
            if parent is None:
                if current:
                    yield current
                current = dict(node, variants=[], metafields=[])
            elif current and parent == current['id'] and '/ProductVariant/' in node.get('id', ''):
                current['variants'].append(dict(node, metafields=[]))
            elif current and '/Metafield/' in node.get('id', ''):
                owner = current if parent == current['id'] else next(
                    (v for v in current['variants'] if v['id'] == parent), None)
                if owner is not None:
                    owner['metafields'].append(node)
        if current:
            yield current

    @api.model
    def _connector_job_shopify_export_stock(self, job):
        """ Send the stock of the linked products to the Shopify locations that have a warehouse:
        the products whose stock moved since the last time, or all of them when asked. """
        store = job.backend
        started = fields.Datetime.now()
        variants = self.env['om.shopify.product'].search([
            ('store_id', '=', store.id), ('tracked', '=', True), ('inventory_item_gid', '!=', False),
            '|', ('product_id.is_storable', '=', True), ('stock_rule', '=', 'fixed'),
        ])
        if store.stock_last_sync and not (job.payload or {}).get('full'):
            moved = self.env['stock.move'].search([
                ('product_id', 'in', variants.product_id.ids),
                ('write_date', '>=', store.stock_last_sync - timedelta(minutes=10)),
            ]).product_id
            variants = variants.filtered(lambda v: v.product_id in moved or v.stock_rule == 'fixed')
        sent = 0
        for location in store.location_ids.filtered(lambda l: l.warehouse_id and l.shopify_active):
            products = variants.product_id.with_context(warehouse_id=location.warehouse_id.id)
            quantities = [{
                'inventoryItemId': variant.inventory_item_gid,
                'locationId': location.shopify_gid,
                'quantity': variant._shopify_stock_quantity(products.browse(variant.product_id.id)[store.stock_field]),
                'changeFromQuantity': None,
            } for variant in variants]
            for start in range(0, len(quantities), STOCK_BATCH):
                batch = quantities[start:start + STOCK_BATCH]
                store._shopify_mutate(queries.INVENTORY_SET, {
                    'input': {'name': 'available', 'reason': 'correction', 'quantities': batch},
                    'key': str(uuid.uuid4()),
                }, 'inventorySetQuantities')
                sent += len(batch)
        store.stock_last_sync = started
        return _("%(count)s stock level(s) sent", count=sent)

    @api.model
    def _cron_shopify_daily(self):
        for store in self._shopify_connected():
            if store.price_auto_export:
                store._connector_enqueue_once('_connector_job_shopify_export_prices', name=_("Send the prices"))
            if store.payout_import and store.payout_journal_id:
                store._connector_enqueue_once('_connector_job_shopify_import_payouts', name=_("Import the payouts"))

    def action_shopify_export_prices(self):
        self._shopify_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_shopify_export_prices', name=_("Send the prices"))
        return self._shopify_notification(_("The prices are being sent: follow it in Jobs."), kind='info')

    def action_shopify_import_stock(self):
        self._shopify_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_shopify_import_stock', name=_("Import the stock"))
        return self._shopify_notification(_("The stock is being imported: follow it in Jobs."), kind='info')

    def action_shopify_import_customers(self):
        self._shopify_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_shopify_fetch_customers', name=_("Import the customers"))
        return self._shopify_notification(_("The customers are being imported: follow it in Jobs."), kind='info')

    def _shopify_check_payout_setup(self):
        self.ensure_one()
        missing = [self._fields[name].string for name in (
            'payout_transit_account_id', 'payout_fee_account_id', 'payout_adjustment_account_id',
            'payout_clearing_account_id', 'payout_entry_journal_id') if not self[name]]
        if missing:
            raise UserError(_("Set the %(fields)s of %(store)s, or click Set Up Payouts.",
                              fields=', '.join(missing), store=self.name))

    def action_shopify_setup_payouts(self):
        """ Create what the payouts need: the transit account, a Shopify Payments journal whose payments
        go on it, its workflow for the payment method shopify_payments, and the accounts of the fees. """
        self.ensure_one()
        company = self.company_id
        Account = self.env['account.account'].with_company(company)

        def account(name, code, account_type, reconcile=False):
            existing = Account.search([('name', '=', name), ('company_ids', 'in', company.ids)], limit=1)
            if existing:
                return existing
            number = int(code)
            while Account.search_count([('code', '=', str(number)), ('company_ids', 'in', company.ids)], limit=1):
                number += 1
            return Account.create({'name': name, 'code': str(number), 'account_type': account_type,
                                   'reconcile': reconcile, 'company_ids': [fields.Command.set(company.ids)]})

        transit = self.payout_transit_account_id or account(_("Shopify Payments Clearing"), '101950', 'asset_current',
                                                            reconcile=True)
        vals = {
            'payout_transit_account_id': transit.id,
            'payout_fee_account_id': (self.payout_fee_account_id
                                      or account(_("Shopify Payments Fees"), '627950', 'expense')).id,
            'payout_adjustment_account_id': (self.payout_adjustment_account_id
                                             or account(_("Shopify Payments Adjustments"), '658950', 'expense')).id,
            'payout_clearing_account_id': (self.payout_clearing_account_id or company.transfer_account_id).id,
            'payout_entry_journal_id': (self.payout_entry_journal_id or self.env['account.journal'].search(
                [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)).id,
            'payout_mode': 'entry',
        }
        Journal = self.env['account.journal'].with_company(company)
        journal = Journal.search([('code', '=', 'SHPAY'), ('company_id', '=', company.id)], limit=1)
        if not journal:
            journal = Journal.create({'name': _("Shopify Payments"), 'code': 'SHPAY', 'type': 'bank',
                                      'company_id': company.id})
        (journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids).payment_account_id = transit
        gateway = self.env['om.shopify.gateway']._shopify_get(self, 'shopify_payments')
        workflow = gateway.workflow_id
        if workflow.journal_id != journal:
            workflow = (workflow or self.workflow_id).copy({'name': _("%(store)s: Shopify Payments", store=self.name),
                                                            'journal_id': journal.id, 'register_payment': True,
                                                            'post_invoice': True})
            gateway.workflow_id = workflow
        self.write(vals)
        return self._shopify_notification(_("Payouts are set up: the payments of Shopify Payments go to the journal "
                                            "%(journal)s, on the account %(account)s.",
                                            journal=journal.name, account=transit.display_name))

    def action_shopify_import_payouts(self):
        self._shopify_ensure_connected()
        for store in self:
            if not store.payout_journal_id:
                raise UserError(_("Set the payout journal of %(store)s.", store=store.name))
            store._connector_enqueue_once('_connector_job_shopify_import_payouts', name=_("Import the payouts"))
        return self._shopify_notification(_("The payouts are being imported: follow it in Jobs."), kind='info')

    # Prices and product export helpers

    def _shopify_prices(self, product):
        """ ``(price, compare-at price or None)`` of ``product`` for Shopify. """
        self.ensure_one()
        price = self.price_pricelist_id._get_product_price(product, 1.0) if self.price_pricelist_id \
            else product.lst_price
        compare_at = None
        if self.compare_pricelist_id:
            compare = self.compare_pricelist_id._get_product_price(product, 1.0)
            if compare > price:
                compare_at = compare
        return price, compare_at

    def _shopify_upload_image(self, template):
        """ Upload the image of ``template`` to Shopify; gives its address for a product. """
        self.ensure_one()
        content = bytes(template.image_1920)
        mimetype = 'image/png' if content[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
        filename = f"product-{template.id}.{'png' if mimetype == 'image/png' else 'jpg'}"
        result = self._shopify_mutate(queries.STAGED_UPLOADS, {'input': [{
            'filename': filename, 'mimeType': mimetype, 'httpMethod': 'POST', 'resource': 'IMAGE',
            'fileSize': str(len(content)),
        }]}, 'stagedUploadsCreate')
        target = (result.get('stagedTargets') or [{}])[0]
        response = request_with_retry(
            'POST', target['url'], data={p['name']: p['value'] for p in target.get('parameters') or []},
            files={'file': (filename, content, mimetype)}, timeout=60)
        if response.status_code >= 300:
            raise UserError(_("Shopify refused the image of %(product)s (HTTP %(status)s).",
                              product=template.name, status=response.status_code))
        return target['resourceUrl']

    def _shopify_publish(self, product_gid):
        self.ensure_one()
        publications = [node for node in self._shopify_paginate(queries.PUBLICATIONS, {}, 'publications')
                        if node.get('name') == 'Online Store']
        if publications:
            self._shopify_mutate(queries.PUBLISH, {'id': product_gid,
                                                   'input': [{'publicationId': publications[0]['id']}]},
                                 'publishablePublish')

    @api.model
    def _connector_job_shopify_export_prices(self, job):
        """ Send the prices and compare-at prices of the linked products. """
        store = job.backend
        count = 0
        templates = self.env['om.shopify.product.template'].search([('store_id', '=', store.id)])
        for template in templates:
            variants = []
            for variant in template.variant_ids:
                price, compare_at = store._shopify_prices(variant.product_id)
                variants.append({'id': variant.external_id, 'price': f'{price:.2f}',
                                 'compareAtPrice': f'{compare_at:.2f}' if compare_at else None})
            if variants:
                store._shopify_mutate(queries.VARIANTS_BULK_UPDATE,
                                      {'productId': template.external_id, 'variants': variants},
                                      'productVariantsBulkUpdate')
                count += len(variants)
        return _("%(count)s price(s) sent", count=count)

    @api.model
    def _connector_job_shopify_import_stock(self, job):
        """ Count the stock of Shopify in the warehouse of each location. """
        store = job.backend
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        variants = {v.inventory_item_gid: v for v in self.env['om.shopify.product'].search(
            [('store_id', '=', store.id), ('inventory_item_gid', '!=', False), ('product_id.is_storable', '=', True)])}
        quants = Quant.browse()
        for location in store.location_ids.filtered(lambda l: l.warehouse_id and l.shopify_active):
            stock_location = location.warehouse_id.lot_stock_id
            for node in store._shopify_paginate(queries.INVENTORY_LEVELS, {'id': location.shopify_gid},
                                                'location.inventoryLevels'):
                variant = variants.get((node.get('item') or {}).get('id'))
                if not variant or variant.product_id.tracking not in (False, 'none'):
                    continue
                available = next((q['quantity'] for q in node.get('quantities') or [] if q['name'] == 'available'), 0)
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

    @api.model
    def _connector_job_shopify_fetch_customers(self, job):
        store = job.backend
        started = fields.Datetime.now()
        search = None
        if store.customer_last_sync:
            search = f"updated_at:>='{self._shopify_search_date(store.customer_last_sync - timedelta(minutes=10))}'"
        count = 0
        for node in store._shopify_paginate(queries.CUSTOMER_IDS, {'query': search}, 'customers'):
            store._connector_enqueue('_connector_job_shopify_import_customer',
                                     {'id': node['id'], 'updatedAt': node['updatedAt']},
                                     model_name='om.shopify.customer',
                                     name=_("Customer %(id)s", id=node['id'].rsplit('/', 1)[-1]),
                                     dedupe_key=f"customer:{node['id']}", priority=30)
            count += 1
        store.customer_last_sync = started
        return _("%(count)s customer(s) to import", count=count)

    @api.model
    def _connector_job_shopify_import_payouts(self, job):
        return self.env['om.shopify.payout']._shopify_import(job.backend)

    def _connector_job_failed(self, job):
        """ An activity for the responsible of the store, once while a failure is not looked at. """
        self.ensure_one()
        self._connector_activity(_("Shopify jobs failed"),
                                 _("%(job)s failed: %(error)s", job=job.name, error=(job.error or '')[:300]))

    # ------------------------------------------------------------------
    # Privacy (GDPR)
    # ------------------------------------------------------------------

    def _shopify_gdpr_customer(self, payload):
        """ ``(partner, orders)`` of the customer of a privacy webhook. """
        self.ensure_one()
        customer = payload.get('customer') or {}
        partner = self.env['res.partner']
        if customer.get('id'):
            partner = self.env['om.shopify.customer']._connector_find(
                self, f"gid://shopify/Customer/{customer['id']}").partner_id
        if not partner and customer.get('email'):
            partner = self.env['res.partner'].search([('email', '=ilike', customer['email']),
                                                      ('parent_id', '=', False)], limit=1)
        order_ids = payload.get('orders_requested') or payload.get('orders_to_redact') or []
        orders = self.env['sale.order'].search([
            ('shopify_store_id', '=', self.id),
            ('shopify_order_gid', 'in', [f'gid://shopify/Order/{i}' for i in order_ids]),
        ]) if order_ids else self.env['sale.order']
        if partner:
            orders |= self.env['sale.order'].search([('shopify_store_id', '=', self.id),
                                                     ('partner_id', 'child_of', partner.id)])
        return partner, orders

    def _shopify_gdpr_activity(self, summary, note):
        self.ensure_one()
        self._connector_activity(summary, note, once=False)

    def _shopify_scrub_jobs(self, needles=None):
        """ Remove the Shopify data kept in the finished jobs: all of them, or those that mention one of
        ``needles`` (an email, an ID). """
        self.ensure_one()
        jobs = self.env['om.connector.job'].sudo().search(
            self._connector_job_domain() + [('state', '!=', 'pending'), ('payload', '!=', False)])
        if needles:
            needles = [str(n) for n in needles if n]
            jobs = jobs.filtered(lambda j: any(n in json.dumps(j.payload) for n in needles))
        jobs.write({'payload': False})
        return len(jobs)

    @api.model
    def _connector_job_shopify_gdpr_data_request(self, job):
        store = job.backend
        partner, orders = store._shopify_gdpr_customer(job.payload)
        customer = job.payload.get('customer') or {}
        store._shopify_gdpr_activity(
            _("GDPR: data request"),
            _("Shopify asks for the data of the customer %(email)s (request %(request)s). Send them what Odoo keeps: "
              "the contact %(partner)s and the orders %(orders)s.",
              email=customer.get('email') or customer.get('id'),
              request=(job.payload.get('data_request') or {}).get('id', ''),
              partner=partner.display_name or _("(none)"),
              orders=', '.join(orders.mapped('name')) or _("(none)")))
        return partner or _("Data request noted")

    @api.model
    def _connector_job_shopify_gdpr_customer_redact(self, job):
        store = job.backend
        customer = job.payload.get('customer') or {}
        partner, orders = store._shopify_gdpr_customer(job.payload)
        self.env['om.shopify.customer']._connector_find(
            store, f"gid://shopify/Customer/{customer.get('id')}").unlink()
        scrubbed = store._shopify_scrub_jobs([customer.get('email'), customer.get('phone'),
                                              f"Customer/{customer.get('id')}"] +
                                             [o.shopify_order_gid for o in orders])
        if partner and store.gdpr_anonymize:
            (partner | partner.child_ids).write({
                'name': _("Redacted customer"), 'email': False, 'phone': False, 'street': False,
                'street2': False, 'city': False, 'zip': False, 'state_id': False, 'vat': False,
                'comment': False, 'active': False,
            })
            result = _("Customer anonymized, %(count)s job(s) cleaned", count=scrubbed)
        else:
            store._shopify_gdpr_activity(
                _("GDPR: erase a customer"),
                _("Shopify asks to erase the customer %(email)s. Odoo removed its link and the Shopify data of "
                  "%(count)s job(s). Decide what to do with the contact %(partner)s and its orders %(orders)s: "
                  "invoices may have to be kept by law.",
                  email=customer.get('email') or customer.get('id'), count=scrubbed,
                  partner=partner.display_name or _("(none)"), orders=', '.join(orders.mapped('name')) or _("(none)")))
            result = _("%(count)s job(s) cleaned, activity for the responsible", count=scrubbed)
        return result

    @api.model
    def _connector_job_shopify_gdpr_shop_redact(self, job):
        store = job.backend
        scrubbed = store._shopify_scrub_jobs()
        self.env['om.shopify.customer'].search([('store_id', '=', store.id)]).unlink()
        store.sudo().write({'access_token': False, 'client_secret': False, 'client_id': False,
                            'token_expires_at': False, 'state': 'error', 'active': False,
                            'last_error': _("Shopify erased the data of this store (the app was uninstalled).")})
        store.message_post(body=_("Shopify asked to erase the data of the store: credentials, customer links and the "
                                  "Shopify data of %(count)s job(s) were removed.", count=scrubbed))
        return _("Store data erased")

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def action_open_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Products of %(store)s", store=self.name),
            'res_model': 'om.shopify.product.template',
            'view_mode': 'list,form',
            'domain': [('store_id', '=', self.id)],
        }

    def action_open_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_shopify.om_shopify_sale_order_action')
        action['domain'] = [('shopify_store_id', '=', self.id)]
        return action

    def action_open_webhooks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Webhooks"),
            'res_model': 'om.shopify.webhook',
            'view_mode': 'list',
            'domain': [('store_id', '=', self.id)],
            'context': {'default_store_id': self.id},
        }
