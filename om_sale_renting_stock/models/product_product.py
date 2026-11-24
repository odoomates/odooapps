from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _rental_get_capacity(self, company=None, warehouse=None):
        """With tracked stock: the units in the warehouse plus the units out on rental."""
        self.ensure_one()
        if not self.is_storable or not warehouse:
            return super()._rental_get_capacity(company=company, warehouse=warehouse)
        locations = warehouse.lot_stock_id | warehouse.rental_location_id
        return self.with_context(location=locations.ids).qty_available
