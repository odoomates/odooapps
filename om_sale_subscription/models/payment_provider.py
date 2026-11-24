from odoo import models


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def _is_tokenization_required(self, **kwargs):
        """Save the payment method when a customer pays a subscription, to charge the next invoices."""
        order = self.env['sale.order']
        if kwargs.get('sale_order_id'):
            order = order.sudo().browse(kwargs['sale_order_id']).exists()
        elif kwargs.get('invoice_id'):
            order = self.env['account.move'].sudo().browse(kwargs['invoice_id']).exists().subscription_id
        if order.is_subscription and order.subscription_state in ('draft', 'progress', 'paused'):
            return True
        return super()._is_tokenization_required(**kwargs)
