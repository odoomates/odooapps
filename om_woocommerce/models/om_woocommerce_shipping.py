from odoo import api, fields, models


class OmWoocommerceShipping(models.Model):
    """ A shipping method of a WooCommerce store (flat_rate "Express", free_shipping…), and the Odoo
    carrier of the orders shipped with it. Made when Odoo meets a new one in an order. """
    _name = 'om.woocommerce.shipping'
    _description = 'WooCommerce Shipping Method'
    _order = 'store_id, title, name'
    _check_company_auto = True

    name = fields.Char(string='Method', required=True, readonly=True,
                       help="The shipping method of WooCommerce: flat_rate, free_shipping, local_pickup…")
    title = fields.Char(readonly=True, help="The title the customer saw at checkout.")
    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    carrier_id = fields.Many2one('delivery.carrier', string='Carrier', check_company=True,
                                 help="The carrier of the orders shipped with this method: the shipping line gets its "
                                      "product, and the deliveries its name and tracking links. Empty: the shipping "
                                      "product of the store.")

    _sql_constraints = [
        ('store_name_title_unique', 'unique (store_id, name, title)',
         "A shipping method is listed once per store."),
    ]

    @api.depends('name', 'title')
    def _compute_display_name(self):
        for method in self:
            method.display_name = f'{method.title} ({method.name})' if method.title else method.name

    @api.model
    def _woo_get(self, store, name, title=None):
        name = name or 'other'
        title = (title or '').strip() or False
        method = self.search([('store_id', '=', store.id), ('name', '=', name), ('title', '=', title)], limit=1)
        return method or self.create({'store_id': store.id, 'name': name, 'title': title})
