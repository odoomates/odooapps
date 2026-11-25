from odoo import models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _website_subscription_lines(self):
        return self.order_line.filtered(
            lambda line: not line.display_type and line.product_id.sudo().is_subscription_product)

    def _website_subscription_plan_for(self, product, plan_id=None):
        """Plan of the cart for `product`: the plan chosen by the customer, the plan of the cart or the
        first plan offered for the product, among the plans published with a price for it."""
        self.ensure_one()
        plans = product.product_tmpl_id._get_website_subscription_plans(
            self.website_id, product=product, pricelist=self.pricelist_id)
        if not plans:
            raise UserError(self.env._(
                '%(product)s cannot be bought online yet: it has no recurring plan published on the website.',
                product=product.display_name))
        plan = plans.filtered(lambda p: p.id == plan_id)
        if not plan and self.subscription_plan_id in plans:
            plan = self.subscription_plan_id
        return plan or plans[:1]

    def _website_set_subscription_plan(self, plan, product):
        """Make the cart a subscription of `plan`; a cart holds the subscription products of one plan."""
        self.ensure_one()
        if self.subscription_plan_id == plan:
            return
        if self.subscription_plan_id and self._website_subscription_lines():
            raise UserError(self.env._(
                'Your cart already holds a subscription billed with the plan "%(plan)s". %(product)s cannot be '
                'added with the plan "%(new_plan)s": complete this order first, or remove the subscription '
                'products from your cart.',
                plan=self.subscription_plan_id.name, product=product.display_name, new_plan=plan.name))
        self.subscription_plan_id = plan

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        plan_id = kwargs.pop('subscription_plan_id', None)
        if self.website_id and quantity > 0:
            product = self.env['product.product'].browse(product_id)
            if product.sudo().is_subscription_product:
                try:
                    plan_id = int(plan_id) if plan_id else None
                except (TypeError, ValueError):
                    plan_id = None
                plan = self._website_subscription_plan_for(product, plan_id)
                self._website_set_subscription_plan(plan, product)
        return super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)

    def _verify_cart_after_update(self):
        self._website_subscription_clear_plan()
        return super()._verify_cart_after_update()

    def _verify_cart(self):
        res = super()._verify_cart()
        self._website_subscription_clear_plan()
        return res

    def _website_subscription_clear_plan(self):
        """A cart without subscription products is not a subscription anymore."""
        for order in self.filtered(lambda o: o.website_id and o.state == 'draft' and o.subscription_plan_id):
            if not order._website_subscription_lines():
                order.subscription_plan_id = False

    def _website_subscription_recurring_amount(self):
        """Total of each period, taxes included as the total of the cart."""
        self.ensure_one()
        return sum(self.order_line.filtered('subscription_recurring').mapped('price_total'))

    def _allow_express_checkout(self):
        # Express checkout does not save the payment method for the next invoices.
        if self.is_subscription and self.website_id.subscription_payment_mode != 'any':
            return False
        return super()._allow_express_checkout()
