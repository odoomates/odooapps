from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

RENTAL_UNITS = [
    ('hour', "Hours"),
    ('day', "Days"),
    ('week', "Weeks"),
    ('month', "Months"),
    ('year', "Years"),
]

UNIT_DELTA = {
    'hour': lambda n: relativedelta(hours=n),
    'day': lambda n: relativedelta(days=n),
    'week': lambda n: relativedelta(weeks=n),
    'month': lambda n: relativedelta(months=n),
    'year': lambda n: relativedelta(years=n),
}


def unit_hours(unit, qty, start=None):
    """Number of hours of `qty` units counted from `start` (calendar months and years)."""
    if not qty:
        return 0
    start = start or fields.Datetime.now()
    delta = (start + UNIT_DELTA[unit](qty)) - start
    return int(delta.total_seconds() // 3600)


class OmRentalPricing(models.Model):
    _name = 'om.rental.pricing'
    _description = "Rental Price"
    _order = 'product_template_id, pricelist_id, unit_sequence, duration, id'
    _check_company_auto = True

    product_template_id = fields.Many2one(
        'product.template', string="Product", required=True, ondelete='cascade', index=True,
        check_company=True)
    product_ids = fields.Many2many(
        'product.product', string="Variants",
        domain="[('product_tmpl_id', '=', product_template_id)]",
        help="Leave empty to use this price for all the variants of the product.")
    pricelist_id = fields.Many2one(
        'product.pricelist', string="Pricelist", ondelete='cascade', check_company=True,
        help="Leave empty to use this price with every pricelist that has no rental price of its own.")
    duration = fields.Integer(string="Duration", required=True, default=1)
    unit = fields.Selection(RENTAL_UNITS, string="Unit", required=True, default='day')
    unit_sequence = fields.Integer(compute='_compute_unit_sequence', store=True)
    price = fields.Monetary(string="Price", currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string="Currency", compute='_compute_currency_id', store=True,
        readonly=False, required=True, precompute=True)
    company_id = fields.Many2one(
        related='product_template_id.company_id', store=True, string="Company")

    _duration_positive = models.Constraint(
        'CHECK(duration > 0)', "The duration of a rental price must be positive.")
    _price_positive = models.Constraint(
        'CHECK(price >= 0)', "The rental price cannot be negative.")

    @api.depends('unit')
    def _compute_unit_sequence(self):
        order = [unit for unit, _label in RENTAL_UNITS]
        for pricing in self:
            pricing.unit_sequence = order.index(pricing.unit) if pricing.unit in order else 0

    @api.depends('pricelist_id', 'product_template_id')
    def _compute_currency_id(self):
        for pricing in self:
            pricing.currency_id = (
                pricing.pricelist_id.currency_id
                or pricing.product_template_id.currency_id
                or self.env.company.currency_id
            )

    @api.depends('duration', 'unit', 'price', 'currency_id')
    def _compute_display_name(self):
        for pricing in self:
            label = pricing._duration_label(pricing.duration)
            pricing.display_name = "%s: %s" % (
                label, pricing.currency_id.format(pricing.price) if pricing.currency_id else pricing.price)

    def _duration_label(self, qty, unit=None):
        unit = unit or self.unit
        labels = self._unit_labels()
        singular, plural = labels.get(unit, (unit, unit))
        return "%s %s" % (qty, singular if qty == 1 else plural)

    @api.model
    def _unit_labels(self):
        return {
            'hour': (self.env._("Hour"), self.env._("Hours")),
            'day': (self.env._("Day"), self.env._("Days")),
            'week': (self.env._("Week"), self.env._("Weeks")),
            'month': (self.env._("Month"), self.env._("Months")),
            'year': (self.env._("Year"), self.env._("Years")),
        }

    def _hours(self, start=None):
        self.ensure_one()
        return max(1, unit_hours(self.unit, self.duration, start))
