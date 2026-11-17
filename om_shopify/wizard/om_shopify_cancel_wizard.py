from odoo import _, fields, models

from ..models.sale_order import CANCEL_REASONS
from ..tools import queries


class OmShopifyCancelWizard(models.TransientModel):
    _name = 'om.shopify.cancel.wizard'
    _description = 'Cancel a Shopify Order'

    order_id = fields.Many2one('sale.order', required=True)
    reason = fields.Selection(CANCEL_REASONS, required=True, default='CUSTOMER')
    refund = fields.Boolean(string='Refund the Payment', default=True,
                            help="Shopify refunds the customer on the payment methods of the order.")
    restock = fields.Boolean(string='Restock in Shopify', default=True)
    notify = fields.Boolean(string='Email the Customer', default=True)
    staff_note = fields.Char(string='Note')

    def action_cancel(self):
        self.ensure_one()
        order = self.order_id
        store = order.shopify_store_id
        store._shopify_mutate(queries.ORDER_CANCEL, {
            'orderId': order.shopify_order_gid,
            'reason': self.reason,
            'refundMethod': {'originalPaymentMethodsRefund': self.refund},
            'restock': self.restock,
            'notifyCustomer': self.notify,
            'staffNote': self.staff_note or None,
        }, 'orderCancel', errors_key='orderCancelUserErrors')
        order.message_post(body=_("Cancellation asked to Shopify (%(reason)s).",
                                  reason=dict(CANCEL_REASONS)[self.reason]))
        order._shopify_cancel({'cancelReason': self.reason})
        return {'type': 'ir.actions.act_window_close'}
