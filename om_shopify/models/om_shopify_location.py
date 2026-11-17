from odoo import api, fields, models

from ..tools import queries


class OmShopifyLocation(models.Model):
    """ A location of a Shopify store, and the Odoo warehouse whose stock it shows. """
    _name = 'om.shopify.location'
    _description = 'Shopify Location'
    _order = 'store_id, sequence, name'
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True)
    sequence = fields.Integer(default=10)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    shopify_gid = fields.Char(string='Shopify ID', required=True, readonly=True)
    active = fields.Boolean(default=True)
    shopify_active = fields.Boolean(string='Active in Shopify', readonly=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse', check_company=True,
        help="The stock of this warehouse is sent to this location. Empty: the stock of this location is not sent.")

    _store_gid_unique = models.Constraint('unique (store_id, shopify_gid)', "A location is imported once per store.")

    @api.model
    def _shopify_import(self, store):
        """ Create or update the locations of ``store``; the first new one gets the warehouse of the store. """
        existing = {loc.shopify_gid: loc for loc in self.with_context(active_test=False).search(
            [('store_id', '=', store.id)])}
        first_mapping = not any(loc.warehouse_id for loc in existing.values())
        for node in store._shopify_paginate(queries.LOCATIONS, {}, 'locations'):
            vals = {'name': node['name'], 'shopify_active': node.get('isActive', True)}
            location = existing.get(node['id'])
            if location:
                location.write(vals)
                continue
            if first_mapping and node.get('isActive', True):
                vals['warehouse_id'] = store.warehouse_id.id
                first_mapping = False
            existing[node['id']] = self.create({'store_id': store.id, 'shopify_gid': node['id'], **vals})
        return self.browse([loc.id for loc in existing.values()])
