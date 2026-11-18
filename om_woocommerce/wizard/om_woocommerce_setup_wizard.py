from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import normalize_site_url


class OmWoocommerceSetupWizard(models.TransientModel):
    """ Connect a store in three steps: the site, the Odoo settings, the first imports. With a REST API
    key, Odoo connects at the first step; with the approval in WordPress, at the end, when WordPress
    sends the administrator back to Odoo. """
    _name = 'om.woocommerce.setup.wizard'
    _description = 'Connect a WooCommerce Store'

    step = fields.Selection([('credentials', 'Site'), ('settings', 'Settings'), ('imports', 'First Imports')],
                            default='credentials', required=True)
    store_id = fields.Many2one('om.woocommerce.store')
    site_url = fields.Char(string='Site Address', help="https://shop.example.com")
    auth_method = fields.Selection([
        ('authorize', 'Approve Odoo in WordPress'),
        ('keys', 'Paste a REST API Key'),
    ], string='Connect By', default='authorize', required=True,
        help="Approve Odoo in WordPress: you log in to WordPress and approve Odoo, which gets its key itself. Odoo "
             "must be reachable at an https address.\nPaste a REST API Key: made in WooCommerce > Settings > "
             "Advanced > REST API.")
    keys_url = fields.Char(string='Make a Key', compute='_compute_keys_url')
    consumer_key = fields.Char(help="WooCommerce > Settings > Advanced > REST API > Add key, with Read/Write "
                                    "permission.")
    consumer_secret = fields.Char()
    webhook_base_url = fields.Char(string='Odoo Public URL', default=lambda self: self._default_public_url(),
                                   help="The https address of this Odoo, reachable from the site: for the webhooks "
                                        "and the approval in WordPress.")
    public_url_ok = fields.Boolean(compute='_compute_public_url_ok')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)

    # Settings
    warehouse_id = fields.Many2one('stock.warehouse', domain="[('company_id', '=', company_id)]",
                                   default=lambda self: self.env['stock.warehouse'].search(
                                       [('company_id', '=', self.env.company.id)], limit=1))
    journal_id = fields.Many2one('account.journal', string='Payment Journal',
                                 domain="[('type', 'in', ('bank', 'cash', 'credit')), ('company_id', '=', company_id)]",
                                 default=lambda self: self.env['account.journal'].search(
                                     [('type', '=', 'bank'), ('company_id', '=', self.env.company.id)], limit=1),
                                 help="Journal of the payments of the paid orders. Empty: orders are invoiced, "
                                      "not paid.")
    tax_mode = fields.Selection([('woocommerce', 'Taxes of WooCommerce'), ('odoo', 'Taxes of Odoo')],
                                default='woocommerce', required=True)
    order_status_ids = fields.Many2many(
        'om.woocommerce.order.status', string='Statuses to Import',
        default=lambda self: self.env['om.woocommerce.order.status'].search(
            [('code', 'in', ('processing', 'completed', 'on-hold'))]))
    product_match = fields.Selection([
        ('sku', 'SKU'),
        ('barcode', 'GTIN, UPC, EAN or ISBN'),
        ('sku_barcode', 'SKU, then GTIN'),
    ], string='Match Products On', default='sku_barcode', required=True)
    product_auto_create = fields.Boolean(string='Create Missing Products', default=True)

    # First imports
    import_products = fields.Boolean(string='Import All Products', default=True)
    import_customers = fields.Boolean(string='Import the Customers')
    import_orders = fields.Boolean(string='Import Orders', default=True)
    order_import_from = fields.Datetime(string='Import Orders From', default=lambda self: fields.Datetime.now())
    export_stock = fields.Boolean(string='Send the Stock', default=True,
                                  help="Every 15 minutes, for the linked products.")
    wp_username = fields.Char(string='WordPress User')
    wp_app_password = fields.Char(string='Application Password',
                                  help="Users > Profile > Application Passwords in WordPress: for the images of the "
                                       "products exported from Odoo. Optional.")
    site_name = fields.Char(related='store_id.site_name')

    @api.model
    def _default_public_url(self):
        url = self.get_base_url() or ''
        return url if url.startswith('https://') else False

    @api.depends('site_url')
    def _compute_keys_url(self):
        for wizard in self:
            url = normalize_site_url(wizard.site_url) if wizard.site_url else ''
            wizard.keys_url = f'{url}/wp-admin/admin.php?page=wc-settings&tab=advanced&section=keys&create-key=1' \
                if url else False

    @api.depends('webhook_base_url')
    def _compute_public_url_ok(self):
        for wizard in self:
            wizard.public_url_ok = bool(wizard.webhook_base_url and wizard.webhook_base_url.startswith('https://'))

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'target': 'new', 'name': _("Connect a WooCommerce Store")}

    def _save_store(self, vals):
        self.ensure_one()
        url = normalize_site_url(self.site_url)
        if not url.startswith('https://'):
            raise UserError(_("WooCommerce accepts a key over https only: %(url)s is not an https address.", url=url))
        vals = {'site_url': url, 'webhook_base_url': self.webhook_base_url, 'company_id': self.company_id.id, **vals}
        store = self.store_id
        if store:
            store.write(vals)
        else:
            host = url.split('://', 1)[-1].split('/')[0].removeprefix('www.')
            store = self.env['om.woocommerce.store'].create({'name': host.split('.')[0].replace('-', ' ').title(),
                                                              **vals})
            self.store_id = store
        return store

    def action_connect(self):
        """ Site step. With a key: connect now. With the approval: the settings first, the approval at
        the end. """
        self.ensure_one()
        if self.auth_method == 'authorize':
            if not self.public_url_ok:
                raise UserError(_("Set the Odoo Public URL (an https address the site can reach), or paste a REST "
                                  "API key instead."))
            self._save_store({})
            self.step = 'settings'
            return self._reopen()
        if not self.consumer_key or not self.consumer_secret:
            raise UserError(_("Set the consumer key and secret."))
        store = self._save_store({'consumer_key': self.consumer_key, 'consumer_secret': self.consumer_secret})
        store.action_woo_connect()
        if store.state != 'connected':
            raise UserError(store.last_error or _("WooCommerce refused the connection."))
        if store.workflow_id.journal_id:
            self.journal_id = store.workflow_id.journal_id
        self.step = 'settings'
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.step = {'imports': 'settings', 'settings': 'credentials'}.get(self.step, 'credentials')
        return self._reopen()

    def action_settings(self):
        self.ensure_one()
        store = self.store_id
        vals = {
            'warehouse_id': self.warehouse_id.id or store.warehouse_id.id,
            'tax_mode': self.tax_mode,
            'order_status_ids': [fields.Command.set(self.order_status_ids.ids)],
            'product_match': self.product_match,
            'product_auto_create': self.product_auto_create,
        }
        if store.site_name:
            vals['name'] = store.site_name
        store.write(vals)
        store.workflow_id.write({'journal_id': self.journal_id.id, 'register_payment': bool(self.journal_id)})
        self.step = 'imports'
        return self._reopen()

    def _pending(self):
        return ','.join(name for name, todo in (
            ('products', self.import_products), ('customers', self.import_customers),
            ('orders', self.import_orders), ('stock', self.export_stock)) if todo)

    def action_finish(self):
        self.ensure_one()
        store = self.store_id
        vals = {'order_import_from': self.order_import_from, 'stock_export': self.export_stock,
                'order_auto_import': self.import_orders}
        if self.wp_username and self.wp_app_password:
            vals.update(wp_username=self.wp_username, wp_app_password=self.wp_app_password)
        store.write(vals)
        store.sudo().setup_pending = self._pending()
        if store.state != 'connected':
            # approval in WordPress: the imports start when WordPress sends the administrator back
            return store.action_woo_authorize()
        store._woo_start_pending()
        return {'type': 'ir.actions.act_window', 'res_model': 'om.woocommerce.store', 'res_id': store.id,
                'view_mode': 'form', 'target': 'current'}
