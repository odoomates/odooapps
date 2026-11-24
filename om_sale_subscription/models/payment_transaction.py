from odoo import fields, models
from odoo.fields import Command


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    subscription_id = fields.Many2one('sale.order', readonly=True,
                                      index='btree_not_null')

    def _post_process(self):
        for tx in self:
            orders = (tx.subscription_id | tx.sale_order_ids | tx.invoice_ids.subscription_id).filtered(
                'is_subscription')
            if tx.state == 'done' and tx.token_id:
                # Keep the payment method of the customer to charge the next invoices.
                orders.filtered(lambda o: not o.subscription_token_id).sudo().subscription_token_id = tx.token_id
            if tx.state in ('done', 'authorized'):
                orders.sudo()._subscription_payment_succeeded(tx)
            elif tx.state in ('error', 'cancel') and tx.subscription_id:
                tx.subscription_id.sudo()._subscription_payment_failed(tx)
        # Invoices posted while processing an online payment are paid by it and sent by the payment flow.
        return super(PaymentTransaction, self.with_context(subscription_skip_post_actions=True))._post_process()

    def _invoice_sale_orders(self):
        # Invoice the first period of the subscriptions paid online, so the payment is reconciled with it.
        res = super()._invoice_sale_orders()
        today = fields.Date.context_today(self)
        for tx in self.filtered(lambda t: t.state == 'done'):
            orders = tx.sale_order_ids.filtered(
                lambda o: o.subscription_state == 'progress' and o._subscription_is_due(today))
            invoices = orders.sudo()._subscription_create_invoices()
            if invoices:
                invoices.action_post()
                tx.invoice_ids = [Command.link(invoice.id) for invoice in invoices]
        return res
