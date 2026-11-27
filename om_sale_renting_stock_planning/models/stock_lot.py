from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    rental_resource_id = fields.Many2one(
        'resource.resource', string="Rental Unit", copy=False, index='btree_not_null',
        ondelete='set null', readonly=True,
        help="Planning resource of the serial number when its product is rented by serial numbers.")

    @api.model_create_multi
    def create(self, vals_list):
        lots = super().create(vals_list)
        lots.filtered(lambda lot: lot.product_id.rental_units_from_serials)._rental_ensure_unit()
        return lots

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            for lot in self.filtered('rental_resource_id'):
                lot.rental_resource_id.sudo().name = lot._rental_unit_name()
        return res

    def _rental_unit_name(self):
        self.ensure_one()
        return f'{self.product_id.name} {self.name}'

    def _rental_ensure_unit(self):
        """ Create the rental unit of the serial numbers (linked both ways) and add it to the
        units of their product. """
        Resource = self.env['resource.resource'].sudo().with_context(active_test=False)
        for lot in self.sudo():
            resource = lot.rental_resource_id or Resource.search([('rental_lot_id', '=', lot.id)], limit=1)
            if not resource:
                resource = Resource.create({
                    'name': lot._rental_unit_name(),
                    'resource_type': 'material',
                    'calendar_id': Resource._planning_around_the_clock_calendar().id,
                    'company_id': lot.company_id.id,
                    'rental_lot_id': lot.id,
                })
            lot.rental_resource_id = resource
            template = lot.product_id.product_tmpl_id
            if resource not in template.rental_unit_ids:
                template.rental_unit_ids = [fields.Command.link(resource.id)]
