from datetime import timedelta

from odoo import fields, models
from odoo.tools.intervals import Intervals


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    rental_product_tmpl_ids = fields.Many2many(
        'product.template', 'om_rental_product_unit_rel', 'resource_id', 'product_tmpl_id',
        string="Rental Products", help="Rental products this unit is rented as.")

    def _rental_busy_intervals(self, start, stop, exclude_slots=None):
        """ Periods the units cannot be rented: booked up to their capacity (rentals, maintenance,
        field service or any other slot), or on leave.

        :return: ``{resource_id: Intervals}`` with aware UTC datetimes
        """
        full = self._planning_full_intervals(start, stop, exclude_slots)
        leaves = self._planning_leave_intervals(start, stop)
        return {resource.id: full[resource.id] | leaves.get(resource.id, Intervals()) for resource in self}

    def _rental_free_units(self, start, stop, exclude_slots=None):
        """ Units free on the whole period (working schedules are ignored: a rental runs day and
        night). """
        if not self or not start or not stop or stop <= start:
            return self.browse()
        busy = self._rental_busy_intervals(start, stop, exclude_slots)
        to_utc = self._planning_utc
        period = Intervals([(to_utc(start), to_utc(stop), self.env['om.planning.slot'])])
        # a minute of tolerance: a booking may end when the next one starts
        tolerance = timedelta(minutes=1)
        free = self.browse()
        for resource in self:
            overlap = busy[resource.id] & period
            if not any(e - s > tolerance for s, e, _recs in overlap):
                free |= resource
        return free

    def _rental_busy_label(self, start, stop, exclude_slots=None):
        """ Short text of what keeps the unit busy in the period. """
        self.ensure_one()
        slots = self._planning_booked_slots(start, stop, exclude_slots)
        labels = [slot._rental_busy_label(self) for slot in slots[:3]]
        if not labels:
            leaves = self.env['resource.calendar.leaves'].sudo().search([
                ('resource_id', '=', self.id),
                ('date_from', '<', stop), ('date_to', '>', start),
            ], limit=3)
            labels = [leave.name or self.env._("unavailable") for leave in leaves]
        return ', '.join(labels) or self.env._("unavailable")
