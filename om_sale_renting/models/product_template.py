import math
from datetime import timedelta

from odoo import api, fields, models

from .rental_pricing import RENTAL_UNITS, unit_hours

# Above this number of hours the exact best combination is not searched (cost of the search),
# the cheapest price per hour is used instead.
MAX_EXACT_HOURS = 24 * 366 * 5


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    rent_ok = fields.Boolean(string="Can be Rented", help="Allow this product to be rented in rental orders.")
    rental_pricing_ids = fields.One2many(
        'om.rental.pricing', 'product_template_id', string="Rental Prices", copy=True)
    rental_extra_hour_price = fields.Monetary(
        string="Extra Hour Price", currency_field='currency_id',
        help="Charged per started hour when the product is returned late.")
    rental_extra_day_price = fields.Monetary(
        string="Extra Day Price", currency_field='currency_id',
        help="Charged per started day when the product is returned late. With an extra hour price "
             "as well, the hours of a day are charged at most one extra day.")
    rental_min_duration = fields.Integer(string="Minimum Duration")
    rental_min_duration_unit = fields.Selection(
        RENTAL_UNITS, string="Minimum Duration Unit", default='day')
    rental_padding_hours = fields.Float(
        string="Preparation Time",
        help="Hours needed after a return before the product can be rented again "
             "(cleaning, checks, transport).")
    rental_qty = fields.Float(
        string="Rentable Quantity", default=1.0, digits='Product Unit',
        help="Number of units that can be rented at the same time, per variant, when the stock "
             "of the product is not tracked.")
    rental_price_display = fields.Char(string="Rental Price", compute='_compute_rental_price_display')

    @api.depends('rental_pricing_ids.price', 'rental_pricing_ids.duration', 'rental_pricing_ids.unit',
                 'rental_pricing_ids.pricelist_id')
    def _compute_rental_price_display(self):
        for template in self:
            pricings = template.rental_pricing_ids.filtered(lambda p: not p.pricelist_id) \
                or template.rental_pricing_ids
            if not pricings:
                template.rental_price_display = False
                continue
            first = pricings.sorted(lambda p: (p.unit_sequence, p.duration, p.id))[0]
            template.rental_price_display = self.env._(
                "%(price)s / %(duration)s",
                price=first.currency_id.format(first.price),
                duration=first._duration_label(first.duration))

    @api.onchange('rent_ok')
    def _onchange_rent_ok(self):
        if self.rent_ok and not self.sale_ok:
            self.sale_ok = True

    # ------------------------------------------------------------
    # Rental price
    # ------------------------------------------------------------

    def _om_rental_get_pricings(self, product=None, pricelist=None):
        """Rental prices that apply to `product` with `pricelist`.

        Prices of the pricelist are used when there are some, otherwise the prices without
        pricelist. Prices of the variant are used when there are some, otherwise the prices
        for all the variants.
        """
        self.ensure_one()
        pricings = self.rental_pricing_ids
        if pricelist and pricings.filtered(lambda p: p.pricelist_id == pricelist):
            pricings = pricings.filtered(lambda p: p.pricelist_id == pricelist)
        else:
            pricings = pricings.filtered(lambda p: not p.pricelist_id)
        if product:
            variant_pricings = pricings.filtered(lambda p: product in p.product_ids)
            pricings = variant_pricings or pricings.filtered(lambda p: not p.product_ids)
        return pricings

    def _om_rental_duration_hours(self, start, stop):
        """Hours charged for a rental from `start` to `stop`, minimum duration included."""
        self.ensure_one()
        if not start or not stop or stop <= start:
            return 0
        hours = math.ceil((stop - start).total_seconds() / 3600 - 1e-6)
        if self.rental_min_duration:
            hours = max(hours, unit_hours(self.rental_min_duration_unit or 'day', self.rental_min_duration, start))
        return max(hours, 1)

    def _om_rental_best_price(self, start, stop, product=None, pricelist=None, currency=None,
                              company=None, date=None):
        """Cheapest combination of rental prices that covers the period.

        :return: dict with `price` (None when the product has no rental price), `hours` and
                 `combination`, a list of (pricing, count).
        """
        self.ensure_one()
        result = {'price': None, 'hours': 0, 'combination': []}
        hours = self._om_rental_duration_hours(start, stop)
        pricings = self._om_rental_get_pricings(product=product, pricelist=pricelist)
        if not hours or not pricings:
            return result
        company = company or self.env.company
        currency = currency or company.currency_id
        date = date or fields.Date.context_today(self)
        options = []
        for pricing in pricings:
            price = pricing.price
            if pricing.currency_id and pricing.currency_id != currency:
                price = pricing.currency_id._convert(price, currency, company, date)
            options.append((pricing, pricing._hours(start), price))
        result['hours'] = hours

        if hours > MAX_EXACT_HOURS:
            pricing, span, price = min(options, key=lambda o: (o[2] / o[1], -o[1]))
            count = math.ceil(hours / span)
            result.update(price=count * price, combination=[(pricing, count)])
            return result

        # best[h]: cheapest cost to cover at least h hours; choice[h]: option used last
        inf = float('inf')
        best = [0.0] + [inf] * hours
        choice = [None] * (hours + 1)
        for h in range(1, hours + 1):
            for index, (_pricing, span, price) in enumerate(options):
                cost = best[max(0, h - span)] + price
                if cost < best[h] - 1e-9:
                    best[h] = cost
                    choice[h] = index
        counts = {}
        h = hours
        while h > 0:
            index = choice[h]
            counts[index] = counts.get(index, 0) + 1
            h = max(0, h - options[index][1])
        combination = sorted(
            ((options[index][0], count) for index, count in counts.items()),
            key=lambda pc: -pc[0]._hours(start))
        result.update(price=best[hours], combination=combination)
        return result

    def _om_rental_combination_label(self, combination):
        """Human readable label of a combination, e.g. "1 Week, 2 Days"."""
        Pricing = self.env['om.rental.pricing']
        totals = {}
        for pricing, count in combination:
            totals[pricing.unit] = totals.get(pricing.unit, 0) + pricing.duration * count
        order = [unit for unit, _label in RENTAL_UNITS]
        return ", ".join(
            Pricing._duration_label(totals[unit], unit) for unit in reversed(order) if totals.get(unit))

    def _om_rental_late_fee(self, delay_hours):
        """Late fee per unit for a delay of `delay_hours` hours."""
        self.ensure_one()
        if delay_hours <= 0:
            return 0.0
        hours = math.ceil(delay_hours - 1e-6)
        hour_price = self.rental_extra_hour_price
        day_price = self.rental_extra_day_price
        if day_price and hour_price:
            days, rest = divmod(hours, 24)
            return days * day_price + min(rest * hour_price, day_price)
        if day_price:
            return math.ceil(hours / 24) * day_price
        return hours * hour_price


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # ------------------------------------------------------------
    # Rental availability
    # ------------------------------------------------------------

    def _rental_get_capacity(self, company=None, warehouse=None):
        """Units of the product that can be rented at the same time."""
        self.ensure_one()
        return self.rental_qty

    def _rental_get_busy_stop(self, stop):
        """End of the period the product is busy for a rental returned at `stop`."""
        self.ensure_one()
        return stop + timedelta(hours=self.rental_padding_hours or 0.0)

    def _rental_get_booked_lines(self, start, stop, exclude_line=None, company=None):
        """Confirmed rental lines of the product that use it between start and stop."""
        self.ensure_one()
        domain = [
            ('is_rental', '=', True),
            ('product_id', '=', self.id),
            ('state', '=', 'sale'),
            ('rental_line_status', 'in', ('reserved', 'pickup')),
            ('rental_start_date', '<', stop),
            '|', ('rental_busy_stop', '>', start), ('rental_line_status', '=', 'pickup'),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if exclude_line and exclude_line._origin.id:
            domain.append(('id', 'not in', exclude_line._origin.ids))
        return self.env['sale.order.line'].sudo().search(domain)

    def _rental_get_available_qty(self, start, stop, exclude_line=None, company=None, warehouse=None):
        """Quantity of the product free for a rental from `start` to `stop`.

        The preparation time of the product is added after `stop`; confirmed rentals that are
        not returned yet are deducted (the highest quantity used at the same time), the lines
        of `exclude_line` excepted.
        """
        self.ensure_one()
        if not start or not stop:
            return 0.0
        busy_stop = self._rental_get_busy_stop(stop)
        lines = self._rental_get_booked_lines(start, busy_stop, exclude_line=exclude_line, company=company)
        capacity = self._rental_get_capacity(company=company, warehouse=warehouse)
        return capacity - lines._om_rental_used_qty(start, busy_stop)

    def _rental_get_next_free_date(self, start, stop, qty, exclude_line=None, company=None, warehouse=None,
                                   horizon_days=366):
        """First datetime from `start` on when `qty` units are free for the same duration.

        :return: datetime, or False when nothing is free within `horizon_days`.
        """
        self.ensure_one()
        if not start or not stop or stop <= start:
            return False
        duration = stop - start
        args = {'exclude_line': exclude_line, 'company': company, 'warehouse': warehouse}
        if self.uom_id.compare(self._rental_get_available_qty(start, stop, **args), qty) >= 0:
            return start
        limit = start + timedelta(days=horizon_days)
        lines = self._rental_get_booked_lines(start, limit, exclude_line=exclude_line, company=company)
        now = fields.Datetime.now()
        candidates = set()
        for line in lines:
            end = line.rental_busy_stop or line.rental_return_date
            if line.rental_line_status == 'pickup' and end < now:
                end = self._rental_get_busy_stop(now)
            if end > start:
                candidates.add(end)
        for candidate in sorted(candidates):
            if candidate > limit:
                break
            available = self._rental_get_available_qty(candidate, candidate + duration, **args)
            if self.uom_id.compare(available, qty) >= 0:
                return candidate
        return False
