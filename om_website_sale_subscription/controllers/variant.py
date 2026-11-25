from odoo.http import request, route

from odoo.addons.website_sale.controllers.variant import WebsiteSaleVariantController


class WebsiteSaleSubscriptionVariantController(WebsiteSaleVariantController):

    @route()
    def get_combination_info_website(
        self, product_template_id, product_id, combination, add_qty, uom_id=None, **kwargs
    ):
        """Return the prices of the plan chosen on the product page."""
        plan_id = kwargs.get('subscription_plan_id')
        if plan_id:
            try:
                request.update_context(website_subscription_plan_id=int(plan_id))
            except (TypeError, ValueError):
                pass
        return super().get_combination_info_website(
            product_template_id, product_id, combination, add_qty, uom_id=uom_id, **kwargs)
