from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    rental_move_ids = fields.One2many('stock.move', 'rental_line_id', string="Rental Moves")
    rental_lot_ids = fields.Many2many(
        'stock.lot', 'om_rental_line_reserved_lot_rel', 'line_id', 'lot_id', string="Reserved Serials",
        domain="[('product_id', '=', product_id)]", copy=False,
        help="Serial numbers set aside for this rental; they are proposed at pickup.")
    rental_pickedup_lot_ids = fields.Many2many(
        'stock.lot', 'om_rental_line_pickedup_lot_rel', 'line_id', 'lot_id', string="Picked Up Serials",
        copy=False, readonly=True)
    rental_returned_lot_ids = fields.Many2many(
        'stock.lot', 'om_rental_line_returned_lot_rel', 'line_id', 'lot_id', string="Returned Serials",
        copy=False, readonly=True)
    rental_tracking = fields.Selection(related='product_id.tracking', string="Rental Tracking")

    def _get_consu_qty_delivered_method(self):
        if self.is_rental:
            return 'manual'
        return super()._get_consu_qty_delivered_method()

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        # rental lines move their stock at pickup and return
        others = self.filtered(lambda line: not line.is_rental)
        return super(SaleOrderLine, others)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)

    @api.depends('is_storable', 'product_uom_qty', 'qty_delivered', 'state', 'move_ids', 'product_uom_id')
    def _compute_qty_to_deliver(self):
        super()._compute_qty_to_deliver()
        self.filtered('is_rental').display_qty_widget = False

    def _rental_get_warehouse(self):
        return self.order_id.warehouse_id

    def _om_rental_out_lots(self):
        """Serials picked up and not returned yet."""
        self.ensure_one()
        return self.rental_pickedup_lot_ids - self.rental_returned_lot_ids

    def _om_rental_moved_out_qty(self):
        """Quantity moved to the rental location and not moved back yet, in the product unit."""
        self.ensure_one()
        rental_location = self._rental_get_warehouse().rental_location_id
        qty = 0.0
        for move in self.rental_move_ids.filtered(lambda m: m.state == 'done'):
            if move.location_dest_id == rental_location:
                qty += move.quantity_product_uom
            elif move.location_id == rental_location:
                qty -= move.quantity_product_uom
        return qty

    def _om_rental_available_lots(self):
        """Serials in the stock of the warehouse, minus those reserved by other rentals of the period."""
        self.ensure_one()
        warehouse = self._rental_get_warehouse()
        if not warehouse or not self.product_id:
            return self.env['stock.lot']
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', '=', self.product_id.id),
            ('location_id', 'child_of', warehouse.lot_stock_id.id),
            ('lot_id', '!=', False),
            ('quantity', '>', 0),
        ])
        lots = quants.lot_id
        if self.rental_start_date and self.rental_return_date:
            busy_stop = self.product_id._rental_get_busy_stop(self.rental_return_date)
            others = self.product_id._rental_get_booked_lines(
                self.rental_start_date, busy_stop, exclude_line=self,
                company=self.company_id or self.order_id.company_id)
            lots -= others.filtered(lambda line: not line.qty_picked_up).rental_lot_ids
        return lots
