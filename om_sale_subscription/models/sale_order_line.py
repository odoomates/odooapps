from odoo import api, fields, models
from odoo.tools import format_date


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    subscription_recurring = fields.Boolean(
        string='Recurring', compute='_compute_subscription_recurring', store=True,
        help='Invoiced every period of the recurring plan of the subscription.')
    subscription_parent_line_id = fields.Many2one('sale.order.line', string='Subscription Line', copy=False,
                                                  index='btree_not_null')

    @api.depends('product_id.is_subscription_product', 'order_id.is_subscription', 'display_type')
    def _compute_subscription_recurring(self):
        for line in self:
            line.subscription_recurring = bool(
                not line.display_type and line.order_id.is_subscription and line.product_id.is_subscription_product)

    @api.depends('subscription_recurring')
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        for line in self.filtered('subscription_recurring'):
            line.qty_to_invoice = 0.0

    @api.depends('subscription_recurring')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        for line in self.filtered(lambda l: l.subscription_recurring and l.state == 'sale'):
            line.invoice_status = 'invoiced' if line.invoice_lines else 'no'

    def _get_display_price(self):
        price = super()._get_display_price()
        order = self.order_id
        if order.subscription_plan_id and self.product_id.is_subscription_product:
            pricing = self.env['om.subscription.pricing']._get_best_pricing(
                self.product_id, order.subscription_plan_id, order.pricelist_id)
            if pricing:
                price = pricing.currency_id._convert(
                    pricing.price, order.currency_id, order.company_id or self.env.company,
                    order.date_order or fields.Date.context_today(self))
            if order.subscription_type == 'upsell':
                price *= order.subscription_prorate_ratio
        return price

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)
        order = self.order_id
        if (order.subscription_type == 'upsell' and order.subscription_prorate_start and not self.display_type
                and 'name' not in optional_values):
            values['name'] = self.env._(
                '%(name)s\nProrated from %(start)s to %(end)s',
                name=self.name,
                start=format_date(self.env, order.subscription_prorate_start),
                end=format_date(self.env, order.subscription_prorate_end),
            )
        return values

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id.filtered(lambda o: o.subscription_state in ('progress', 'paused'))._subscription_sync_log()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {'product_uom_qty', 'price_unit', 'discount', 'product_id'} & set(vals):
            self.order_id.filtered(
                lambda o: o.subscription_state in ('progress', 'paused'))._subscription_sync_log()
        return res

    def unlink(self):
        orders = self.order_id.filtered(lambda o: o.subscription_state in ('progress', 'paused'))
        res = super().unlink()
        orders._subscription_sync_log()
        return res
