from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools.client import is_valid_shop_domain, normalize_shop_domain


class OmShopifySetupWizard(models.TransientModel):
    """ Connect a store in three steps: credentials, Odoo settings, first imports. """
    _name = 'om.shopify.setup.wizard'
    _description = 'Connect a Shopify Store'

    step = fields.Selection([('credentials', 'Credentials'), ('settings', 'Settings'), ('imports', 'First Imports')],
                            default='credentials', required=True)
    store_id = fields.Many2one('om.shopify.store')
    shop_domain = fields.Char(string='Store Address', help="my-store.myshopify.com")
    auth_type = fields.Selection([
        ('client_credentials', 'Client ID and Secret (Dev Dashboard app)'),
        ('oauth', 'Install by Link (OAuth)'),
        ('token', 'Admin API Access Token (custom app)'),
    ], string='Authentication', default='client_credentials', required=True)
    client_id = fields.Char(string='Client ID')
    client_secret = fields.Char(string='Client Secret')
    access_token = fields.Char(string='Access Token')
    webhook_base_url = fields.Char(string='Odoo Public URL', help="https address of this Odoo, for the webhooks.")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    warehouse_id = fields.Many2one('stock.warehouse', domain="[('company_id', '=', company_id)]")
    journal_id = fields.Many2one('account.journal', string='Payment Journal',
                                 domain="[('type', 'in', ('bank', 'cash', 'credit')), ('company_id', '=', company_id)]",
                                 help="Journal of the payments of the paid orders. Empty: orders are invoiced, not paid.")
    tax_mode = fields.Selection([('shopify', 'Taxes of Shopify'), ('odoo', 'Taxes of Odoo')], default='shopify',
                                required=True)
    import_products = fields.Boolean(string='Import All Products', default=True)
    order_import_from = fields.Datetime(string='Import Orders From', default=lambda self: fields.Datetime.now())
    export_stock = fields.Boolean(string='Send the Stock', default=True)
    shop_name = fields.Char(related='store_id.shop_name')

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'target': 'new', 'name': _("Connect a Shopify Store")}

    def action_connect(self):
        self.ensure_one()
        domain = normalize_shop_domain(self.shop_domain)
        if not is_valid_shop_domain(domain):
            raise UserError(_("%(domain)s is not a store address: it looks like my-store.myshopify.com.", domain=domain))
        vals = {
            'name': domain.split('.')[0].replace('-', ' ').title(),
            'shop_domain': domain,
            'auth_type': self.auth_type,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'access_token': self.access_token if self.auth_type == 'token' else False,
            'webhook_base_url': self.webhook_base_url,
            'company_id': self.company_id.id,
        }
        store = self.store_id
        if store:
            store.write(vals)
        else:
            store = self.env['om.shopify.store'].create(vals)
            self.store_id = store
        if self.auth_type == 'oauth':
            # Shopify asks the merchant, then comes back to the store
            return store.action_shopify_oauth_start()
        store.action_shopify_connect()
        if store.state != 'connected':
            raise UserError(store.last_error or _("Shopify refused the connection."))
        self.write({'step': 'settings', 'warehouse_id': store.warehouse_id.id,
                    'journal_id': store.workflow_id.journal_id.id, 'webhook_base_url': store.webhook_base_url})
        return self._reopen()

    def action_settings(self):
        self.ensure_one()
        store = self.store_id
        store.write({'warehouse_id': self.warehouse_id.id or store.warehouse_id.id, 'tax_mode': self.tax_mode})
        store.workflow_id.write({'journal_id': self.journal_id.id, 'register_payment': bool(self.journal_id)})
        self.step = 'imports'
        return self._reopen()

    def action_finish(self):
        self.ensure_one()
        store = self.store_id
        store.order_import_from = self.order_import_from
        store.stock_export = self.export_stock
        if self.import_products:
            store.action_shopify_import_products()
        store.action_shopify_import_orders()
        return {'type': 'ir.actions.act_window', 'res_model': 'om.shopify.store', 'res_id': store.id,
                'view_mode': 'form', 'target': 'current'}
