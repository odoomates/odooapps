from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    rental_units_from_serials = fields.Boolean(
        string="Serial Numbers as Units",
        help="Each serial number of the product is a rental unit in the planning: the serial booked "
             "on the order is picked up and returned.")

    @api.onchange('rental_units_from_serials')
    def _onchange_rental_units_from_serials(self):
        if self.rental_units_from_serials:
            self.rental_availability = 'unit'

    def write(self, vals):
        res = super().write(vals)
        if vals.get('rental_units_from_serials'):
            self._rental_sync_serial_units()
        return res

    def _rental_sync_serial_units(self):
        """ Rental units for the serial numbers of the products rented by serial numbers. """
        templates = self.filtered('rental_units_from_serials')
        if not templates:
            return
        templates.filtered(lambda t: t.rental_availability != 'unit').rental_availability = 'unit'
        lots = self.env['stock.lot'].sudo().search([('product_id.product_tmpl_id', 'in', templates.ids)])
        lots._rental_ensure_unit()
