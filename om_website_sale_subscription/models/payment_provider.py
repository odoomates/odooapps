from odoo import models


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def _get_website_subscription_order(self, values):
        """The website subscription being paid in the payment context `values`, if any."""
        order_id = values.get('sale_order_id')
        if not order_id:
            return self.env['sale.order']
        order = self.env['sale.order'].sudo().browse(int(order_id)).exists()
        if order.website_id and order.is_subscription and order.state in ('draft', 'sent'):
            return order
        return self.env['sale.order']

    def _is_tokenization_required(self, **kwargs):
        required = super()._is_tokenization_required(**kwargs)
        if required and not self:
            # Searching the available providers: keep those that cannot save the payment method when
            # the website allows it. A provider that can save it still saves it.
            order = self._get_website_subscription_order(kwargs)
            if order and order.website_id.subscription_payment_mode == 'any':
                return False
        return required

    def _find_available_payment_methods(
        self, partner_id, *, currency_id=None, force_tokenization=False, is_express_checkout=False,
        report=None, **kwargs
    ):
        if not force_tokenization:
            order = self._get_website_subscription_order(kwargs)
            force_tokenization = bool(order) and order.website_id.subscription_payment_mode != 'any'
        return super()._find_available_payment_methods(
            partner_id, currency_id=currency_id, force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout, report=report, **kwargs)
