from odoo import api, fields, models


class OmWoocommerceGateway(models.Model):
    """ A payment method of a WooCommerce store (stripe, paypal, bacs, cod…), and the workflow of the
    orders paid with it. Made when Odoo meets a new one in an order. """
    _name = 'om.woocommerce.gateway'
    _description = 'WooCommerce Payment Method'
    _order = 'store_id, name'
    _check_company_auto = True

    name = fields.Char(string='Code', required=True, readonly=True)
    title = fields.Char(readonly=True)
    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    workflow_id = fields.Many2one('om.connector.order.workflow', string='Workflow', required=True, check_company=True)

    _store_name_unique = models.Constraint('unique (store_id, name)', "A payment method is listed once per store.")

    @api.depends('name', 'title')
    def _compute_display_name(self):
        for gateway in self:
            gateway.display_name = f'{gateway.title} ({gateway.name})' if gateway.title else gateway.name

    @api.model
    def _woo_get(self, store, name, title=None):
        name = name or 'manual'
        gateway = self.search([('store_id', '=', store.id), ('name', '=', name)], limit=1)
        if gateway:
            if title and not gateway.title:
                gateway.title = title
            return gateway
        return self.create({'store_id': store.id, 'name': name, 'title': title or False,
                            'workflow_id': store.workflow_id.id})
