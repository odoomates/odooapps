from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.fields import Command


class OmPlanningSlot(models.Model):
    _inherit = 'om.planning.slot'

    rental_line_id = fields.Many2one(
        'sale.order.line', string="Rental Line", index='btree_not_null', ondelete='cascade', copy=False)
    rental_order_id = fields.Many2one(related='rental_line_id.order_id', string="Rental Order")
    rental_partner_id = fields.Many2one(related='rental_line_id.order_partner_id', string="Rental Customer")
    rental_slot_type = fields.Selection([
        ('unit', "Rented Unit"),
        ('staff_out', "Delivery"),
        ('staff_in', "Collection"),
    ], string="Rental Booking", copy=False)
    rental_state = fields.Selection([
        ('reserved', "Reserved"),
        ('pickup', "Picked Up"),
        ('returned', "Returned"),
    ], string="Rental Status", copy=False)

    def _rental_busy_label(self, resource=None):
        """ Short text of the slot for the availability messages of rentals. """
        self.ensure_one()
        what = self.rental_order_id.name or self.source_name or self.name or self.role_id.name \
            or self.env._("booking")
        tz = ZoneInfo((resource and resource.tz) or self.env.user.tz or 'UTC')
        start = self.start_datetime.replace(tzinfo=UTC).astimezone(tz)
        end = self.end_datetime.replace(tzinfo=UTC).astimezone(tz)
        label = f"{what} ({start:%m/%d %H:%M} - {end:%m/%d %H:%M})"
        if self.rental_line_id.rental_is_late:
            label = self.env._("%(booking)s, late return", booking=label)
        return label

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('om_rental_no_sync') \
                and {'start_datetime', 'end_datetime', 'resource_ids'} & set(vals):
            self.filtered(lambda s: s.rental_line_id and s.rental_slot_type == 'unit')._rental_sync_line()
        return res

    def _rental_sync_line(self):
        """ A rented unit moved on the Gantt: the line gets the new unit, and new dates while it
        is reserved (pickup) or out (return). """
        for slot in self:
            line = slot.rental_line_id.sudo()
            if line.state != 'sale' or slot.rental_state == 'returned':
                continue
            product = line.product_id
            units = slot.material_resource_ids or slot.resource_ids.filtered(lambda r: r.resource_type == 'material')
            line_units = line.rental_unit_ids
            others = line.rental_slot_ids.filtered(lambda s: s.rental_slot_type == 'unit' and s != slot)
            new_units = units | (line_units & others.resource_ids)
            line_vals = {}
            if set(new_units.ids) != set(line_units.ids):
                line_vals['rental_unit_ids'] = [Command.set(new_units.ids)]
            if slot.rental_state == 'reserved':
                start = slot.start_datetime + timedelta(hours=product.rental_padding_before_hours or 0.0)
                if start != line.rental_start_date:
                    line_vals['rental_start_date'] = start
            stop = slot.end_datetime - timedelta(hours=product.rental_padding_hours or 0.0)
            if stop != line.rental_return_date and stop > (line_vals.get('rental_start_date') or line.rental_start_date):
                line_vals['rental_return_date'] = stop
            if line_vals:
                line.write(line_vals)

    def _planning_check(self):
        """ A rented unit runs day and night: time outside its working schedule is no conflict. """
        result = super()._planning_check()
        for slot in self.filtered(lambda s: s.rental_slot_type == 'unit'):
            key = slot.id
            if key in result:
                result[key] = [problem for problem in result[key] if problem['type'] != 'outside']
        return result
