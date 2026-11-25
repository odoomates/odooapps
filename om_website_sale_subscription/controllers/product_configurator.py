from odoo.http import request

from odoo.addons.website_sale.controllers.product_configurator import (
    WebsiteSaleProductConfiguratorController,
)


class WebsiteSaleSubscriptionConfiguratorController(WebsiteSaleProductConfiguratorController):

    def _get_basic_product_information(
        self, product_or_template, pricelist, combination, currency=None, date=None, uom=None, **kwargs
    ):
        """Show the recurring price of subscription products in the product configurator."""
        info = super()._get_basic_product_information(
            product_or_template, pricelist, combination, currency=currency, date=date, uom=uom, **kwargs)
        if not request.is_frontend or not product_or_template.sudo().is_subscription_product:
            return info
        is_variant = product_or_template.is_product_variant
        template = product_or_template.product_tmpl_id if is_variant else product_or_template
        plans = template._get_website_subscription_prices(
            self.env.website, product_or_template if is_variant else None, pricelist)
        if not plans:
            return info
        plan_ids = [plan['id'] for plan in plans]
        try:
            plan_id = int(kwargs.get('subscription_plan_id') or 0)
        except (TypeError, ValueError):
            plan_id = 0
        if plan_id not in plan_ids:
            cart_plan_id = request.cart.subscription_plan_id.id if request.cart else False
            plan_id = cart_plan_id if cart_plan_id in plan_ids else plan_ids[0]
        plan = next(plan for plan in plans if plan['id'] == plan_id)
        info['price'] = plan['price']
        info['description_sale'] = self.env._(
            '%(plan)s subscription, billed every %(period)s', plan=plan['name'], period=plan['period'])
        for key in ('strikethrough_price', 'base_unit_price', 'base_unit_name'):
            info.pop(key, None)
        return info
