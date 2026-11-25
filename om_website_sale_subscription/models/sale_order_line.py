from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_website_subscription_period(self):
        """Billing period shown next to the price of a recurring line on the website, e.g. "month"."""
        self.ensure_one()
        if not self.subscription_recurring:
            return ''
        return self.order_id.subscription_plan_id.sudo()._get_website_period_label()
