from datetime import timedelta

from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_view_rental_unit_schedule(self):
        """ The button of the product form shows on the variant form too, which Odoo builds from it. """
        self.ensure_one()
        return self.product_tmpl_id.action_view_rental_unit_schedule()

    def _rental_by_units(self):
        self.ensure_one()
        return self.rental_availability == 'unit'

    def _rental_units(self, company=None):
        """ Active units of the product (of the company or shared). """
        self.ensure_one()
        units = self.product_tmpl_id.sudo().rental_unit_ids.filtered('active')
        if company:
            units = units.filtered(lambda unit: not unit.company_id or unit.company_id == company)
        return units

    def _rental_unit_period(self, start, stop):
        """ Period a unit is booked for a rental from ``start`` to ``stop``: preparation time
        before the pickup and after the return included. """
        self.ensure_one()
        return start - timedelta(hours=self.rental_padding_before_hours or 0.0), self._rental_get_busy_stop(stop)

    def _rental_get_capacity(self, company=None, warehouse=None):
        self.ensure_one()
        if self._rental_by_units():
            return float(len(self._rental_units(company)))
        return super()._rental_get_capacity(company=company, warehouse=warehouse)

    def _rental_get_available_qty(self, start, stop, exclude_line=None, company=None, warehouse=None):
        """ By units: the number of units free in the planning for the period. """
        self.ensure_one()
        if not self._rental_by_units():
            return super()._rental_get_available_qty(
                start, stop, exclude_line=exclude_line, company=company, warehouse=warehouse)
        if not start or not stop:
            return 0.0
        exclude = exclude_line._origin.sudo().rental_slot_ids if exclude_line else None
        unit_start, unit_stop = self._rental_unit_period(start, stop)
        return float(len(self._rental_units(company)._rental_free_units(unit_start, unit_stop, exclude)))

    def _rental_get_next_free_date(self, start, stop, qty, exclude_line=None, company=None, warehouse=None,
                                   horizon_days=366):
        """ By units: the first pickup date from ``start`` on when ``qty`` units are free for the
        same duration, from the bookings of the units in the planning. """
        self.ensure_one()
        if not self._rental_by_units():
            return super()._rental_get_next_free_date(
                start, stop, qty, exclude_line=exclude_line, company=company, warehouse=warehouse,
                horizon_days=horizon_days)
        if not start or not stop or stop <= start:
            return False
        args = {'exclude_line': exclude_line, 'company': company, 'warehouse': warehouse}
        if self._rental_get_available_qty(start, stop, **args) >= qty:
            return start
        units = self._rental_units(company)
        if len(units) < qty:
            return False
        duration = stop - start
        limit = start + timedelta(days=horizon_days)
        before = timedelta(hours=self.rental_padding_before_hours or 0.0)
        exclude = exclude_line._origin.sudo().rental_slot_ids if exclude_line else None
        busy = units._rental_busy_intervals(start - before, limit + duration, exclude)
        candidates = set()
        for intervals in busy.values():
            for _s, e, _recs in intervals:
                candidate = e.replace(tzinfo=None) + before
                if start < candidate <= limit:
                    candidates.add(candidate)
        for candidate in sorted(candidates):
            if self._rental_get_available_qty(candidate, candidate + duration, **args) >= qty:
                return candidate
        return False
