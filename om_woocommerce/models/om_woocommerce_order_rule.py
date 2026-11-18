from odoo import fields, models


class OmWoocommerceOrderRule(models.Model):
    """ What an imported order gets when it matches: a workflow, a warehouse, or both. The first
    rule that matches gives each of them; what no rule gives comes from the payment method, then
    from the store. Covers for example "cash on delivery: no payment", or "made at the counter:
    shipped from the shop". """
    _name = 'om.woocommerce.order.rule'
    _description = 'WooCommerce Order Rule'
    _order = 'store_id, sequence, id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    gateway_id = fields.Many2one('om.woocommerce.gateway', string='Payment Method', check_company=True,
                                 domain="[('store_id', '=', store_id)]", help="Empty: any payment method.")
    status_id = fields.Many2one('om.woocommerce.order.status', string='Status', help="Empty: any.")
    created_via = fields.Char(string='Created Via',
                              help="How the order was made in WooCommerce: checkout, admin, rest-api, store-api… "
                                   "Empty: any.")
    shipping_method = fields.Char(help="The ID of a shipping method of the order: flat_rate, free_shipping, "
                                       "local_pickup… Empty: any.")
    workflow_id = fields.Many2one('om.connector.order.workflow', string='Workflow', check_company=True)
    warehouse_id = fields.Many2one('stock.warehouse', check_company=True)

    def _matches(self, data, gateway):
        self.ensure_one()
        methods = {(line.get('method_id') or '').lower() for line in data.get('shipping_lines') or []}
        return (
            (not self.gateway_id or self.gateway_id == gateway)
            and (not self.status_id or self.status_id.code == data.get('status'))
            and (not self.created_via or self.created_via.lower() == (data.get('created_via') or '').lower())
            and (not self.shipping_method or self.shipping_method.lower() in methods)
        )
