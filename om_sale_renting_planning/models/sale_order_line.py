import math
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.misc import format_datetime


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    rental_by_units = fields.Boolean(compute='_compute_rental_by_units', string="Rented by Units")
    rental_allowed_unit_ids = fields.Many2many(
        'resource.resource', compute='_compute_rental_allowed_unit_ids', string="Allowed Units")
    rental_unit_ids = fields.Many2many(
        'resource.resource', 'om_rental_line_unit_rel', 'line_id', 'resource_id', string="Booked Units",
        copy=False, domain="[('id', 'in', rental_allowed_unit_ids)]",
        help="Units booked for this rental. Free units are chosen at the confirmation when empty.")
    rental_slot_ids = fields.One2many('om.planning.slot', 'rental_line_id', string="Rental Bookings")
    rental_unit_busy = fields.Boolean(compute='_compute_rental_unit_warning', string="Unit Busy")
    rental_unit_warning = fields.Text(compute='_compute_rental_unit_warning', string="Unit Warnings")
    rental_next_free_date = fields.Datetime(
        compute='_compute_rental_next_free_date', string="Next Free Date",
        help="First pickup date when the quantity is free for the same duration.")

    @api.depends('is_rental', 'product_id.rental_availability')
    def _compute_rental_by_units(self):
        for line in self:
            line.rental_by_units = bool(line.is_rental and line.product_id.rental_availability == 'unit')

    @api.depends('rental_by_units', 'product_id', 'order_id.company_id')
    def _compute_rental_allowed_unit_ids(self):
        for line in self:
            if line.rental_by_units:
                line.rental_allowed_unit_ids = line.product_id._rental_units(
                    line.company_id or line.order_id.company_id)
            else:
                line.rental_allowed_unit_ids = False

    @api.depends('rental_by_units', 'rental_unit_ids', 'rental_start_date', 'rental_return_date', 'state',
                 'rental_line_status')
    def _compute_rental_unit_warning(self):
        for line in self:
            messages = []
            if line.rental_by_units and line.rental_start_date and line.rental_return_date \
                    and line.state in ('draft', 'sent', 'sale') and line.rental_line_status != 'returned':
                exclude = line._origin.sudo().rental_slot_ids
                start, stop = line.product_id._rental_unit_period(line.rental_start_date, line.rental_return_date)
                units = line.rental_unit_ids._origin.sudo()
                if line.state != 'sale':
                    free = units._rental_free_units(start, stop, exclude)
                    for unit in units - free:
                        messages.append(self.env._(
                            "%(unit)s is not free: %(busy)s",
                            unit=unit.name, busy=unit._rental_busy_label(start, stop, exclude)))
                else:
                    for slot in exclude.filtered(lambda s: s.rental_slot_type == 'unit' and s.has_conflict):
                        count = len(messages)
                        for unit in slot.resource_ids:
                            others = unit._planning_booked_slots(slot.start_datetime, slot.end_datetime, slot)
                            others = others.filtered(lambda o: not o.role_id.allow_overlap)
                            if len(others) >= max(unit.planning_capacity, 1):
                                messages.append(self.env._(
                                    "%(unit)s is also booked: %(busy)s", unit=unit.name,
                                    busy=', '.join(other._rental_busy_label(unit) for other in others[:3])))
                        if len(messages) == count:
                            messages.append(slot.conflict_info)
            line.rental_unit_busy = bool(messages)
            line.rental_unit_warning = '\n'.join(dict.fromkeys(messages)) or False

    @api.depends('rental_by_units', 'rental_unavailable', 'product_uom_qty', 'rental_start_date',
                 'rental_return_date')
    def _compute_rental_next_free_date(self):
        for line in self:
            if line.rental_by_units and line.rental_unavailable:
                line.rental_next_free_date = line._om_rental_next_free_date()
            else:
                line.rental_next_free_date = False

    @api.onchange('rental_unit_ids')
    def _onchange_rental_unit_ids(self):
        if self.rental_unit_busy:
            return {'warning': {'title': self.env._("Unit not free"), 'message': self.rental_unit_warning}}
        return None

    def write(self, vals):
        res = super().write(vals)
        if {'rental_unit_ids', 'product_uom_qty'} & set(vals) and not self.env.context.get('om_rental_no_sync'):
            self.filtered(lambda line: line.is_rental and line.state == 'sale')._rental_sync_booking()
        return res

    # ------------------------------------------------------------
    # Bookings in the planning
    # ------------------------------------------------------------

    def _rental_sync_booking(self):
        res = super()._rental_sync_booking()
        if not self.env.context.get('om_rental_no_sync'):
            self.filtered('is_rental')._rental_planning_sync()
        return res

    def _rental_unit_qty(self):
        """ Number of units the line needs. """
        self.ensure_one()
        qty = self.product_uom_id._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
        return max(int(math.ceil(qty - 1e-6)), 0)

    def _rental_unit_period(self):
        self.ensure_one()
        return self.product_id._rental_unit_period(self.rental_start_date, self.rental_return_date)

    def _rental_unit_slots(self):
        self.ensure_one()
        return self.sudo().rental_slot_ids.filtered(lambda s: s.rental_slot_type == 'unit')

    def _rental_picked_units(self):
        """ Units out with the customer (or back): the units already picked up first, then the
        others in the order of the line, up to the picked up quantity. """
        self.ensure_one()
        count = int(math.floor(self.qty_picked_up + 1e-6))
        slots = self._rental_unit_slots()
        units = self.rental_unit_ids
        done = slots.filtered(lambda s: s.rental_state in ('pickup', 'returned')).resource_ids & units
        return (done | (units - done))[:count]

    def _rental_returned_units(self):
        """ Units back from the customer, among the picked up units. """
        self.ensure_one()
        count = int(math.floor(self.qty_returned + 1e-6))
        picked = self._rental_picked_units()
        slots = self._rental_unit_slots()
        done = slots.filtered(lambda s: s.rental_state == 'returned').resource_ids & picked
        return (done | (picked - done))[:count]

    def _rental_planning_assign_units(self):
        """ Complete the units of the line with free units (raises when there are not enough). """
        self.ensure_one()
        qty = self._rental_unit_qty()
        units = self.rental_unit_ids
        if len(units) > qty:
            # keep the units already out
            picked = self._rental_picked_units()
            units = (picked | (units - picked))[:qty]
        elif len(units) < qty:
            start, stop = self._rental_unit_period()
            company = self.company_id or self.order_id.company_id
            candidates = self.product_id._rental_units(company) - units
            free = candidates._rental_free_units(start, stop, self._rental_unit_slots())
            missing = qty - len(units)
            if len(free) < missing:
                message = self.env._(
                    "Only %(free)s unit(s) of %(product)s are free from %(start)s to %(stop)s (%(qty)s needed).",
                    free=len(free) + len(units), product=self.product_id.display_name, qty=qty,
                    start=format_datetime(self.env, self.rental_start_date, tz=self._om_rental_tz(), dt_format='short'),
                    stop=format_datetime(self.env, self.rental_return_date, tz=self._om_rental_tz(), dt_format='short'))
                next_free = self._om_rental_next_free_date()
                if next_free:
                    message += "\n" + self.env._(
                        "They are free for the same duration from %(date)s.",
                        date=format_datetime(self.env, next_free, tz=self._om_rental_tz(), dt_format='short'))
                raise UserError(message)
            units |= free[:missing]
        if set(units.ids) != set(self.rental_unit_ids.ids):
            self.with_context(om_rental_no_sync=True).rental_unit_ids = [Command.set(units.ids)]
        return units

    def _rental_planning_sync(self):
        """ Book the units (and the staff) of confirmed rental lines by units in the planning:
        one slot per unit from the pickup to the return, preparation time included. The pickup
        and the return move the slots, a late return extends them; a cancelled line frees them. """
        Slot = self.env['om.planning.slot'].sudo().with_context(
            om_rental_no_sync=True, om_planning_keep_published=True, recurrence_update='this')
        now = fields.Datetime.now().replace(second=0, microsecond=0)
        for line in self:
            slots = line.sudo().rental_slot_ids.with_context(Slot.env.context)
            if not line.rental_by_units or line.state != 'sale' or not line.rental_start_date \
                    or not line.rental_return_date or line.rental_line_status == 'cancel':
                slots.unlink()
                continue
            units = line._rental_planning_assign_units()
            unit_slots = slots.filtered(lambda s: s.rental_slot_type == 'unit')
            (unit_slots.filtered(lambda s: not (s.resource_ids & units))).unlink()
            unit_slots = unit_slots.exists()
            start, stop = line._rental_unit_period()
            after = timedelta(hours=line.product_id.rental_padding_hours or 0.0)
            picked = line._rental_picked_units()
            returned = line._rental_returned_units()
            company = line.company_id or line.order_id.company_id
            for unit in units:
                slot = unit_slots.filtered(lambda s: unit in s.resource_ids)[:1]
                if unit in returned:
                    state = 'returned'
                    slot_start = slot.start_datetime if slot else start
                    slot_stop = slot.end_datetime if slot and slot.rental_state == 'returned' \
                        else max(now + after, slot_start + timedelta(minutes=1))
                elif unit in picked:
                    state = 'pickup'
                    slot_start = slot.start_datetime if slot and slot.rental_state == 'pickup' else min(start, now)
                    slot_stop = max(stop, now + after) if now > line.rental_return_date else stop
                else:
                    state = 'reserved'
                    slot_start, slot_stop = start, stop
                values = {
                    'name': line._rental_slot_name(),
                    'start_datetime': slot_start,
                    'end_datetime': slot_stop,
                    'rental_state': state,
                }
                if slot:
                    slot.write({key: value for key, value in values.items() if slot[key] != value})
                else:
                    Slot.create({
                        **values,
                        'resource_ids': [Command.set(unit.ids)],
                        'rental_line_id': line.id,
                        'rental_slot_type': 'unit',
                        'source_ref': f'sale.order,{line.order_id.id}',
                        'company_id': company.id,
                        'state': 'published',
                    })
            line._rental_planning_sync_staff(slots.filtered(lambda s: s.rental_slot_type in ('staff_out', 'staff_in')))
        return True

    def _rental_slot_name(self):
        self.ensure_one()
        partner = self.order_partner_id.commercial_partner_id.name or ''
        return ' - '.join(filter(None, [self.order_id.name, self.product_id.display_name, partner]))

    def _rental_planning_sync_staff(self, staff_slots):
        """ Delivery slot before the pickup and collection slot after the return for the staff
        role of the product: free people of the role are proposed, an open slot otherwise. """
        self.ensure_one()
        template = self.product_id.product_tmpl_id.sudo()
        role = template.rental_staff_role_id
        if not role:
            staff_slots.unlink()
            return
        hours = timedelta(hours=template.rental_staff_hours or 1.0)
        company = self.company_id or self.order_id.company_id
        periods = {
            'staff_out': (self.rental_start_date - hours, self.rental_start_date),
            'staff_in': (self.rental_return_date, self.rental_return_date + hours),
        }
        names = {
            'staff_out': self.env._("Delivery: %s", self._rental_slot_name()),
            'staff_in': self.env._("Collection: %s", self._rental_slot_name()),
        }
        for slot_type, (start, stop) in periods.items():
            slot = staff_slots.filtered(lambda s: s.rental_slot_type == slot_type)[:1]
            if slot:
                if slot.start_datetime != start or slot.end_datetime != stop:
                    slot.write({'start_datetime': start, 'end_datetime': stop})
                continue
            people = role._planning_find_free(start, stop, qty=max(template.rental_staff_count, 1))
            people = people.filtered(lambda r: not r.company_id or r.company_id == company)
            staff_slots.create({
                'name': names[slot_type],
                'role_id': role.id,
                'resource_ids': [Command.set(people.ids)],
                'start_datetime': start,
                'end_datetime': stop,
                'rental_line_id': self.id,
                'rental_slot_type': slot_type,
                'source_ref': f'sale.order,{self.order_id.id}',
                'company_id': company.id,
            })

    @api.model
    def _cron_rental_planning_late(self):
        """ Extend the bookings of the units not returned on time, so that the clash with the
        next booking of the unit shows. """
        lines = self.search([
            ('is_rental', '=', True),
            ('state', '=', 'sale'),
            ('rental_line_status', '=', 'pickup'),
            ('rental_return_date', '<', fields.Datetime.now()),
            ('product_id.rental_availability', '=', 'unit'),
        ])
        lines._rental_planning_sync()

    @api.model
    def _rental_planning_demo_set_unit(self, order_id, equipment_id):
        """ Demo data: book a given equipment on the rental lines of an order. """
        order = self.env['sale.order'].browse(order_id)
        equipment = self.env['maintenance.equipment'].browse(equipment_id)
        order.order_line.filtered('rental_by_units').rental_unit_ids = [Command.set(equipment.resource_id.ids)]
