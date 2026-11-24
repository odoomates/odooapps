import math
from datetime import timedelta

from odoo import api, fields, models
from odoo.tools.misc import format_amount, format_datetime

RENTAL_LINE_STATUS = [
    ('draft', "Quotation"),
    ('reserved', "Reserved"),
    ('pickup', "Picked Up"),
    ('returned', "Returned"),
    ('cancel', "Cancelled"),
]


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_rental = fields.Boolean(
        string="Rental", compute='_compute_is_rental', store=True, readonly=False, precompute=True)
    rental_start_date = fields.Datetime(
        string="Pickup Date", compute='_compute_rental_dates', store=True, readonly=False,
        precompute=True, index=True)
    rental_return_date = fields.Datetime(
        string="Return Date", compute='_compute_rental_dates', store=True, readonly=False,
        precompute=True, index=True)
    rental_busy_stop = fields.Datetime(
        string="Available Again", compute='_compute_rental_busy_stop', store=True,
        help="Return date plus the preparation time of the product.")
    qty_picked_up = fields.Float(string="Picked Up", digits='Product Unit', copy=False)
    qty_returned = fields.Float(string="Returned", digits='Product Unit', copy=False)
    rental_line_status = fields.Selection(
        RENTAL_LINE_STATUS, string="Rental Line Status", compute='_compute_rental_line_status',
        store=True)
    rental_duration_label = fields.Char(string="Charged Duration", compute='_compute_rental_duration_label')
    rental_available_qty = fields.Float(
        string="Available", compute='_compute_rental_availability', digits='Product Unit',
        help="Quantity still free for the rental period, other confirmed rentals deducted.")
    rental_unavailable = fields.Boolean(compute='_compute_rental_availability')
    rental_is_late = fields.Boolean(string="Late Return", compute='_compute_rental_is_late')

    _rental_line_period_check = models.Constraint(
        'CHECK(rental_start_date IS NULL OR rental_return_date IS NULL '
        'OR rental_return_date > rental_start_date)',
        "The return date of a rental line must be after its pickup date.",
    )

    # ------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------

    @api.depends('product_id', 'order_id.is_rental_order', 'display_type')
    def _compute_is_rental(self):
        for line in self:
            line.is_rental = bool(
                line.order_id.is_rental_order and line.product_id.rent_ok and not line.display_type)

    @api.depends('is_rental', 'order_id.rental_start_date', 'order_id.rental_return_date')
    def _compute_rental_dates(self):
        for line in self:
            if line.is_rental:
                line.rental_start_date = line.order_id.rental_start_date
                line.rental_return_date = line.order_id.rental_return_date
            else:
                line.rental_start_date = False
                line.rental_return_date = False

    @api.depends('rental_return_date', 'product_id.rental_padding_hours')
    def _compute_rental_busy_stop(self):
        for line in self:
            if line.rental_return_date:
                line.rental_busy_stop = line.rental_return_date + timedelta(
                    hours=line.product_id.rental_padding_hours or 0.0)
            else:
                line.rental_busy_stop = False

    @api.depends('is_rental', 'state', 'product_uom_qty', 'qty_picked_up', 'qty_returned')
    def _compute_rental_line_status(self):
        for line in self:
            if not line.is_rental:
                line.rental_line_status = False
            elif line.state in ('draft', 'sent'):
                line.rental_line_status = 'draft'
            elif line.state == 'cancel':
                line.rental_line_status = 'cancel'
            elif line.qty_returned >= line.product_uom_qty:
                line.rental_line_status = 'returned'
            elif line.qty_picked_up > line.qty_returned:
                line.rental_line_status = 'pickup'
            else:
                line.rental_line_status = 'reserved'

    @api.depends('is_rental', 'product_id', 'rental_start_date', 'rental_return_date')
    def _compute_rental_duration_label(self):
        for line in self:
            line.rental_duration_label = line._om_rental_charged_label() if line.is_rental else False

    @api.depends('is_rental', 'rental_line_status', 'rental_return_date')
    def _compute_rental_is_late(self):
        now = fields.Datetime.now()
        for line in self:
            line.rental_is_late = bool(
                line.is_rental and line.rental_line_status in ('reserved', 'pickup')
                and line.rental_return_date and line.rental_return_date < now)

    @api.depends('is_rental', 'product_id', 'product_uom_qty', 'product_uom_id', 'rental_start_date',
                 'rental_return_date', 'state', 'qty_picked_up', 'order_id.company_id')
    def _compute_rental_availability(self):
        for line in self:
            if not line._om_rental_check_availability():
                line.rental_available_qty = 0.0
                line.rental_unavailable = False
                continue
            available = line._om_rental_free_qty()
            needed = line.product_uom_id._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
            line.rental_available_qty = available
            line.rental_unavailable = line.product_id.uom_id.compare(needed, available) > 0

    @api.depends("order_partner_id", "order_id", "product_id")
    def _compute_display_name(self):
        if not self.env.context.get('om_rental_schedule'):
            super()._compute_display_name()
            return
        for line in self:
            line.display_name = "%s - %s (%s)" % (
                line.order_id.name, line.product_id.display_name, line.order_partner_id.display_name)

    # ------------------------------------------------------------
    # Price and description
    # ------------------------------------------------------------

    def _om_rental_priced(self):
        self.ensure_one()
        return bool(self.is_rental and self.product_id and self.rental_start_date and self.rental_return_date)

    def _om_rental_best_price(self):
        self.ensure_one()
        order = self.order_id
        return self.product_id.product_tmpl_id._om_rental_best_price(
            self.rental_start_date, self.rental_return_date, product=self.product_id,
            pricelist=order.pricelist_id, currency=self.currency_id or order.currency_id,
            company=self.company_id or order.company_id or self.env.company,
            date=fields.Date.to_date(order.date_order) if order.date_order else None,
        )

    def _get_display_price(self):
        if self._om_rental_priced():
            price = self._om_rental_best_price()['price']
            if price is not None:
                return price
        return super()._get_display_price()

    def _om_rental_charged_label(self):
        self.ensure_one()
        if not self._om_rental_priced():
            return False
        best = self._om_rental_best_price()
        if best['combination']:
            return self.product_id.product_tmpl_id._om_rental_combination_label(best['combination'])
        return self._om_rental_format_span(self.rental_start_date, self.rental_return_date)

    def _get_rental_pricing_description(self):
        """Short rental pricing note used by the order emails of Sales and eCommerce."""
        self.ensure_one()
        label = self._om_rental_charged_label()
        if not label:
            return ''
        return self.env._(
            "Rental: %(duration)s for %(price)s", duration=label,
            price=format_amount(self.env, self.price_unit, self.currency_id or self.order_id.currency_id))

    @api.model
    def _om_rental_format_span(self, start, stop):
        if not start or not stop or stop <= start:
            return False
        hours = math.ceil((stop - start).total_seconds() / 3600 - 1e-6)
        days, hours = divmod(hours, 24)
        Pricing = self.env['om.rental.pricing']
        parts = []
        if days:
            parts.append(Pricing._duration_label(days, 'day'))
        if hours:
            parts.append(Pricing._duration_label(hours, 'hour'))
        return " ".join(parts)

    def _om_rental_tz(self):
        return self.env.user.tz or self.order_id.user_id.tz or 'UTC'

    def _om_rental_period_prefix(self):
        return self.env._("Rental:")

    def _om_rental_period_text(self):
        self.ensure_one()
        tz = self._om_rental_tz()
        return self.env._(
            "%(prefix)s %(start)s to %(stop)s (%(duration)s)",
            prefix=self._om_rental_period_prefix(),
            start=format_datetime(self.env, self.rental_start_date, tz=tz, dt_format='short'),
            stop=format_datetime(self.env, self.rental_return_date, tz=tz, dt_format='short'),
            duration=self._om_rental_charged_label() or '',
        )

    def _get_sale_order_line_multiline_description_sale(self):
        description = super()._get_sale_order_line_multiline_description_sale()
        if self._om_rental_priced():
            description = "\n".join(filter(None, [description, self._om_rental_period_text()]))
        return description

    def _om_rental_name_with_period(self):
        self.ensure_one()
        line = self
        lang = self.order_id._get_lang()
        if lang and lang != self.env.lang:
            line = self.with_context(lang=lang)
        prefix = line._om_rental_period_prefix()
        kept = [part for part in (self.name or '').split("\n") if not part.startswith(prefix)]
        if line._om_rental_priced():
            kept.append(line._om_rental_period_text())
        return "\n".join(part for part in kept if part)

    def _om_rental_update_lines(self):
        """Update the price and the period in the description after a change of dates."""
        for line in self:
            if not line.product_id or line.display_type:
                continue
            if line.state in ('draft', 'sent') and not line.qty_invoiced:
                currency = line.currency_id or line.company_id.currency_id or self.env.company.currency_id
                manual_price = currency.compare_amounts(line.technical_price_unit, line.price_unit)
                if not manual_price:
                    line._reset_price_unit()
            line.name = line._om_rental_name_with_period()

    @api.onchange('rental_start_date', 'rental_return_date', 'is_rental')
    def _onchange_rental_period(self):
        self._om_rental_update_lines()

    @api.onchange('product_id', 'product_uom_qty', 'rental_start_date', 'rental_return_date')
    def _onchange_rental_availability(self):
        if self.rental_unavailable:
            message = self.env._(
                "Only %(available)s %(uom)s of %(product)s are free for this period.",
                available=self.rental_available_qty,
                uom=self.product_id.uom_id.name,
                product=self.product_id.display_name,
            )
            next_free = self._om_rental_next_free_date()
            if next_free:
                message += "\n" + self.env._(
                    "The quantity is free for the same duration from %(date)s.",
                    date=format_datetime(self.env, next_free, tz=self._om_rental_tz(), dt_format='short'))
            return {'warning': {'title': self.env._("Not available"), 'message': message}}
        return None

    def write(self, vals):
        res = super().write(vals)
        if 'rental_start_date' in vals or 'rental_return_date' in vals:
            rental_lines = self.filtered('is_rental')
            if 'price_unit' not in vals:
                rental_lines._om_rental_update_lines()
            rental_lines.filtered(lambda line: line.state == 'sale')._rental_sync_booking()
        return res

    # ------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------

    def _om_rental_check_availability(self):
        self.ensure_one()
        return bool(
            self.is_rental and self.product_id and self.rental_start_date and self.rental_return_date
            and self.state in ('draft', 'sent', 'sale') and not self.qty_picked_up
        )

    def _rental_get_warehouse(self):
        """Warehouse the line is rented from (none without stock)."""
        return None

    def _om_rental_availability_args(self):
        self.ensure_one()
        return {
            'exclude_line': self,
            'company': self.company_id or self.order_id.company_id,
            'warehouse': self._rental_get_warehouse(),
        }

    def _om_rental_free_qty(self):
        self.ensure_one()
        return self.product_id._rental_get_available_qty(
            self.rental_start_date, self.rental_return_date, **self._om_rental_availability_args())

    def _om_rental_next_free_date(self):
        self.ensure_one()
        qty = self.product_uom_id._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
        return self.product_id._rental_get_next_free_date(
            self.rental_start_date, self.rental_return_date, qty, **self._om_rental_availability_args())

    def _om_rental_used_qty(self, start, stop):
        """Highest quantity used at the same time by these lines between start and stop."""
        now = fields.Datetime.now()
        events = []
        for line in self:
            line_start, line_stop = line.rental_start_date, line.rental_busy_stop or line.rental_return_date
            if line.rental_line_status == 'pickup' and line_stop < now:
                # late: still out, busy at least until now plus the preparation time
                line_stop = now + timedelta(hours=line.product_id.rental_padding_hours or 0.0)
            begin, end = max(line_start, start), min(line_stop, stop)
            if begin >= end:
                continue
            qty = line.product_uom_id._compute_quantity(
                line.product_uom_qty - line.qty_returned, line.product_id.uom_id)
            if qty <= 0:
                continue
            events.append((begin, 1, qty))
            events.append((end, 0, -qty))
        used = peak = 0.0
        for _date, _kind, qty in sorted(events, key=lambda e: (e[0], e[1])):
            used += qty
            peak = max(peak, used)
        return peak

    # ------------------------------------------------------------
    # Bookings
    # ------------------------------------------------------------

    def _rental_sync_booking(self):
        """Hook called when rental lines are confirmed, picked up, returned, cancelled or
        get new dates, so that other modules can keep their bookings up to date."""
        return True

    # ------------------------------------------------------------
    # Pickup and return
    # ------------------------------------------------------------

    def _om_rental_late_hours(self, when=None):
        self.ensure_one()
        when = when or fields.Datetime.now()
        if not self.rental_return_date or when <= self.rental_return_date:
            return 0.0
        return (when - self.rental_return_date).total_seconds() / 3600
