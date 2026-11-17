from odoo import api, fields, models


class OmShopifyGateway(models.Model):
    """ A payment method of a Shopify store (shopify_payments, manual, paypal…), and the workflow of
    the orders paid with it. Made when Odoo meets a new one in an order. """
    _name = 'om.shopify.gateway'
    _description = 'Shopify Payment Method'
    _order = 'store_id, name'
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    workflow_id = fields.Many2one('om.connector.order.workflow', string='Workflow', required=True, check_company=True)

    _store_name_unique = models.Constraint('unique (store_id, name)', "A payment method is listed once per store.")

    @api.model
    def _shopify_get(self, store, name):
        name = name or 'manual'
        gateway = self.search([('store_id', '=', store.id), ('name', '=', name)], limit=1)
        return gateway or self.create({'store_id': store.id, 'name': name, 'workflow_id': store.workflow_id.id})
