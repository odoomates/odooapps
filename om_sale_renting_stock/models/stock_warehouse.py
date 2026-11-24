from odoo import api, fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    rental_location_id = fields.Many2one(
        'stock.location', string="Rental Location", check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
        help="Products picked up by rental customers are moved to this location until they are returned. "
             "It is outside the warehouse so that rented products are not counted in its stock.")

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        warehouses._om_rental_create_location()
        return warehouses

    def _om_rental_create_location(self):
        for warehouse in self.filtered(lambda wh: not wh.rental_location_id):
            warehouse.rental_location_id = self.env['stock.location'].with_company(warehouse.company_id).create({
                'name': self.env._("%(code)s Rental", code=warehouse.code),
                'usage': 'internal',
                'company_id': warehouse.company_id.id,
            })
