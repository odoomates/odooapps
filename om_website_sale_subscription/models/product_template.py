from odoo import fields, models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_website_subscription_pricings(self, website, product=None, pricelist=None):
        """Recurring price of each plan offered on `website`, by plan sequence.

        :param website: the website selling the product.
        :param product: the variant; without it, the lowest price of the variants is used.
        :param pricelist: the pricelist of the customer.
        :return: list of (plan, pricing) tuples, in sudo.
        """
        self.ensure_one()
        template = self.sudo()
        if not template.is_subscription_product:
            return []
        pricelist = (pricelist or self.env['product.pricelist']).sudo()
        product = (product or self.env['product.product']).sudo()
        pricings = template.subscription_pricing_ids.filtered(
            lambda p: p.plan_id._is_website_available(website))
        result = []
        for plan in pricings.plan_id.sorted(lambda p: (p.sequence, p.id)):
            if product:
                pricing = self.env['om.subscription.pricing'].sudo()._get_best_pricing(product, plan, pricelist)
            else:
                plan_pricings = pricings.filtered(
                    lambda p, plan=plan: p.plan_id == plan and (not p.pricelist_id or p.pricelist_id == pricelist))
                if plan_pricings.filtered('pricelist_id'):
                    plan_pricings = plan_pricings.filtered('pricelist_id')
                pricing = plan_pricings.sorted('price')[:1]
            if pricing:
                result.append((plan, pricing))
        return result

    def _get_website_subscription_plans(self, website, product=None, pricelist=None):
        plans = self.env['om.subscription.plan'].sudo()
        for plan, _pricing in self._get_website_subscription_pricings(website, product, pricelist):
            plans |= plan
        return plans

    def _get_website_subscription_prices(self, website, product=None, pricelist=None, fiscal_position=None):
        """Recurring prices of the plans offered on `website`, with taxes shown as on the shop.

        :return: list of dicts with the plan id, name, price and period.
        """
        self.ensure_one()
        currency = website.currency_id
        company = website.company_id
        today = fields.Date.context_today(self)
        product_or_template = (product or self).sudo()
        product_taxes = product_or_template.taxes_id._filter_taxes_by_company()
        if fiscal_position is None:
            fiscal_position = getattr(request, 'fiscal_position', None) if request else None
            fiscal_position = fiscal_position or self.env['account.fiscal.position']
        taxes = fiscal_position.map_tax(product_taxes) if product_taxes else product_taxes
        values = []
        for plan, pricing in self._get_website_subscription_pricings(website, product, pricelist):
            price = pricing.currency_id._convert(pricing.price, currency, company, today)
            values.append({
                'id': plan.id,
                'name': plan.name,
                'price': self._apply_taxes_to_price(
                    price, currency, product=product, product_taxes=product_taxes, taxes=taxes,
                    website=website),
                'period': plan._get_website_period_label(),
            })
        return values

    def _website_is_subscription(self):
        """Whether the product is sold as a subscription on the current website."""
        self.ensure_one()
        return bool(self.sudo().is_subscription_product and self._get_website_subscription_pricings(
            self.env.website, pricelist=getattr(request, 'pricelist', None) if request else None))

    def _get_additional_combination_info(
        self, product_or_template, quantity, uom, website, pricelist, fiscal_position, **kwargs
    ):
        info = super()._get_additional_combination_info(
            product_or_template, quantity, uom, website, pricelist, fiscal_position, **kwargs)
        if not self.sudo().is_subscription_product:
            return info
        product = product_or_template if product_or_template.is_product_variant else None
        plans = self._get_website_subscription_prices(website, product, pricelist, fiscal_position)
        info['subscription_plans'] = plans
        if not plans:
            return info
        plan_ids = [plan['id'] for plan in plans]
        selected_id = self.env.context.get('website_subscription_plan_id')
        if selected_id not in plan_ids:
            cart = getattr(request, 'cart', None) if request else None
            cart_plan_id = cart.subscription_plan_id.id if cart else False
            selected_id = cart_plan_id if cart_plan_id in plan_ids else plan_ids[0]
        selected = next(plan for plan in plans if plan['id'] == selected_id)
        info.update({
            'subscription_plan_id': selected_id,
            'subscription_period': selected['period'],
            'price': selected['price'],
            'list_price': selected['price'],
            'has_discounted_price': False,
            'compare_list_price': 0,
        })
        info.pop('base_unit_price', None)
        return info

    def _get_sales_prices(self, pricelist_sudo, fiscal_position_sudo, website):
        prices = super()._get_sales_prices(pricelist_sudo, fiscal_position_sudo, website)
        for template in self.filtered(lambda t: t.sudo().is_subscription_product):
            plans = template._get_website_subscription_prices(
                website, pricelist=pricelist_sudo, fiscal_position=fiscal_position_sudo)
            if not plans:
                continue
            cheapest = min(plans, key=lambda plan: plan['price'])
            vals = prices[template.id]
            vals.update({
                'subscription_price': cheapest['price'],
                'subscription_period': cheapest['period'],
                'subscription_plan_count': len(plans),
            })
            if website.subscription_show_recurring_price:
                vals['price_reduce'] = cheapest['price']
                vals.pop('base_price', None)
                vals.pop('base_unit_price', None)
        return prices
