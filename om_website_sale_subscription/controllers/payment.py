from odoo.exceptions import ValidationError

from odoo.addons.website_sale.controllers.payment import PaymentPortal


class WebsiteSaleSubscriptionPaymentPortal(PaymentPortal):

    def _validate_transaction_for_order(self, _transaction, _sale_order):
        """Subscriptions bought online save the payment method, unless the website allows otherwise."""
        super()._validate_transaction_for_order(_transaction, _sale_order)
        order = _sale_order.sudo()
        if (order.is_subscription and order.website_id.subscription_payment_mode != 'any'
                and not (_transaction.tokenize or _transaction.token_id)):
            raise ValidationError(self.env._(
                'This order is a subscription: pay it with a payment method that can be saved for the '
                'next invoices.'))
