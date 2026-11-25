from odoo import fields, models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _post_process(self):
        super()._post_process()
        today = fields.Date.context_today(self)
        for tx in self.filtered(lambda t: t.state == 'done' and t.operation != 'validation'):
            if tx.company_id.sale_automatic_invoice:
                continue  # The sales flow already invoices the paid orders.
            orders = tx.sale_order_ids.filtered(
                lambda o: o.website_id.subscription_invoice_at_payment
                and o.subscription_state == 'progress' and o._subscription_is_due(today))
            if orders:
                tx._website_subscription_invoice(orders)

    def _website_subscription_invoice(self, orders):
        """Invoice the first period of the subscriptions paid on the website, as the automatic invoicing
        of the sales flow does: create and post the invoice, pay it with this payment and send it."""
        self.ensure_one()
        tx = self.with_company(self.company_id).with_context(subscription_skip_post_actions=True)
        invoices_before = tx.invoice_ids
        tx._invoice_sale_orders()
        invoices = tx.invoice_ids - invoices_before
        if not invoices:
            return
        invoices.filtered(lambda inv: inv.state == 'draft').action_post()
        for order in orders.sudo():
            for invoice in invoices.filtered(lambda inv: inv.payment_state in ('not_paid', 'partial')):
                order._subscription_reconcile_payments(invoice)
        if not self.env.context.get('skip_sale_auto_invoice_send'):
            # Sent after the commit, as the automatic invoicing of the sales flow does.
            tx._send_invoice()
