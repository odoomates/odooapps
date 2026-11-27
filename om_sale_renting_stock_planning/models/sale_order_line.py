from odoo import models
from odoo.fields import Command


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _rental_serial_units(self):
        """ Whether the units of the line are serial numbers. """
        self.ensure_one()
        return bool(self.rental_by_units and self.product_id.rental_units_from_serials)

    def _rental_unit_of_lots(self, lots):
        return lots.sudo().rental_resource_id

    def _rental_picked_units(self):
        """ Serial units: the units of the serial numbers picked up. """
        self.ensure_one()
        if not self._rental_serial_units():
            return super()._rental_picked_units()
        return self._rental_unit_of_lots(self.rental_pickedup_lot_ids)

    def _rental_returned_units(self):
        self.ensure_one()
        if not self._rental_serial_units():
            return super()._rental_returned_units()
        return self._rental_unit_of_lots(self.rental_returned_lot_ids & self.rental_pickedup_lot_ids)

    def _rental_planning_assign_units(self):
        """ Serial units: a serial picked up instead of the booked one takes its place, and the
        booked serials are set aside for the pickup. """
        self.ensure_one()
        if self._rental_serial_units() and self.rental_pickedup_lot_ids:
            picked = self._rental_unit_of_lots(self.rental_pickedup_lot_ids)
            qty = self._rental_unit_qty()
            units = picked | (self.rental_unit_ids - picked)[:max(qty - len(picked), 0)]
            if set(units.ids) != set(self.rental_unit_ids.ids):
                self.with_context(om_rental_no_sync=True).rental_unit_ids = [Command.set(units.ids)]
        units = super()._rental_planning_assign_units()
        if self._rental_serial_units():
            lots = units.rental_lot_id
            if set(lots.ids) != set(self.rental_lot_ids.ids) and not self.qty_picked_up:
                self.with_context(om_rental_no_sync=True).rental_lot_ids = [Command.set(lots.ids)]
        return units

    def write(self, vals):
        res = super().write(vals)
        if 'rental_unit_ids' in vals:
            for line in self.filtered(lambda l: l._rental_serial_units() and not l.qty_picked_up):
                lots = line.rental_unit_ids.rental_lot_id
                if set(lots.ids) != set(line.rental_lot_ids.ids):
                    line.with_context(om_rental_no_sync=True).rental_lot_ids = [Command.set(lots.ids)]
        elif 'rental_lot_ids' in vals and not self.env.context.get('om_rental_no_sync'):
            for line in self.filtered(lambda l: l._rental_serial_units() and not l.qty_picked_up):
                units = line.rental_lot_ids.sudo().rental_resource_id
                if units and set(units.ids) != set(line.rental_unit_ids.ids):
                    line.rental_unit_ids = [Command.set(units.ids)]
        return res
