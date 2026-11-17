import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import queries


class AccountMove(models.Model):
    _inherit = 'account.move'

    shopify_store_id = fields.Many2one('om.shopify.store', string='Shopify Store', readonly=True, copy=False,
                                       index='btree_not_null')
    shopify_refund_gid = fields.Char(string='Shopify Refund', readonly=True, copy=False)
    shopify_order_id = fields.Many2one('sale.order', compute='_compute_shopify_order_id', string='Shopify Order')

    @api.depends('invoice_line_ids.sale_line_ids', 'reversed_entry_id')
    def _compute_shopify_order_id(self):
        for move in self:
            orders = (move.invoice_line_ids.sale_line_ids.order_id
                      | move.reversed_entry_id.invoice_line_ids.sale_line_ids.order_id)
            move.shopify_order_id = orders.filtered('shopify_store_id')[:1]

    def action_shopify_refund(self):
        """ Refund this credit note in Shopify: the lines, the shipping, and the money on the payment
        methods of the order. """
        for move in self:
            if move.move_type != 'out_refund' or move.state != 'posted':
                raise UserError(_("Only a posted credit note is refunded in Shopify."))
            if move.shopify_refund_gid:
                raise UserError(_("%(move)s is already refunded in Shopify.", move=move.name))
            order = move.shopify_order_id
            if not order:
                raise UserError(_("%(move)s is not the credit note of a Shopify order.", move=move.name))
            order.shopify_store_id._connector_enqueue(
                '_connector_job_shopify_refund', {'move_id': move.id}, model_name='account.move',
                name=_("Refund %(order)s in Shopify (%(move)s)", order=order.shopify_order_name, move=move.name),
                dedupe_key=f'refund:{move.id}', max_attempts=3)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': _("The refund is being sent to Shopify."), 'type': 'info'},
        }

    @api.model
    def _connector_job_shopify_refund(self, job):
        move = self.browse(job.payload['move_id']).exists()
        if not move or move.shopify_refund_gid:
            return _("Nothing to refund")
        return move._shopify_refund(job.backend)

    def _shopify_refund(self, store):
        self.ensure_one()
        order = self.shopify_order_id
        lines, shipping = [], 0.0
        location = store.location_ids.filtered(lambda l: l.warehouse_id == order.warehouse_id)[:1]
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            gid = line.sale_line_ids[:1].shopify_line_gid
            if gid and line.quantity:
                refund_line = {'lineItemId': gid, 'quantity': int(line.quantity),
                               'restockType': store.refund_restock_type}
                if store.refund_restock_type == 'RETURN' and location:
                    refund_line['locationId'] = location.shopify_gid
                lines.append(refund_line)
            elif line.product_id == store.shipping_product_id:
                shipping += line.price_total
        suggestion = store._shopify_execute(queries.SUGGESTED_REFUND, {
            'id': order.shopify_order_gid,
            'lines': [{k: v for k, v in l.items() if k in ('lineItemId', 'quantity', 'restockType', 'locationId')}
                      for l in lines],
            'shipping': f'{shipping:.2f}' if shipping else None,
        }).get('order', {}).get('suggestedRefund') or {}
        remaining = self.amount_total
        transactions = []
        for suggested in suggestion.get('suggestedTransactions') or []:
            available = float(((suggested.get('amountSet') or {}).get('shopMoney') or {}).get('amount') or 0.0)
            take = min(available, remaining)
            if take <= 0:
                continue
            transactions.append({
                'orderId': order.shopify_order_gid,
                'parentId': (suggested.get('parentTransaction') or {}).get('id'),
                'gateway': suggested.get('gateway'),
                'kind': 'REFUND',
                'amount': f'{take:.2f}',
            })
            remaining -= take
        refund_input = {
            'orderId': order.shopify_order_gid,
            'note': self.ref or self.name,
            'notify': store.refund_notify,
            'refundLineItems': lines,
            'transactions': transactions,
        }
        if shipping:
            refund_input['shipping'] = {'amount': f'{shipping:.2f}'}
        result = store._shopify_mutate(queries.REFUND_CREATE, {'input': refund_input, 'key': str(uuid.uuid4())},
                                       'refundCreate')
        self.write({'shopify_refund_gid': (result.get('refund') or {}).get('id'), 'shopify_store_id': store.id})
        if remaining > 0.01:
            self.message_post(body=_("Shopify could refund %(amount)s less than this credit note on the payment "
                                     "methods of the order.", amount=self.currency_id.format(remaining)))
        return self
