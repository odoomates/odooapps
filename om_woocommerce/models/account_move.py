from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    woo_store_id = fields.Many2one('om.woocommerce.store', string='WooCommerce Store', readonly=True, copy=False,
                                   index='btree_not_null')
    woo_refund_id = fields.Char(string='WooCommerce Refund', readonly=True, copy=False)
    woo_order_id = fields.Many2one('sale.order', compute='_compute_woo_order_id', string='WooCommerce Order')

    @api.depends('invoice_line_ids.sale_line_ids', 'reversed_entry_id')
    def _compute_woo_order_id(self):
        for move in self:
            orders = (move.invoice_line_ids.sale_line_ids.order_id
                      | move.reversed_entry_id.invoice_line_ids.sale_line_ids.order_id)
            move.woo_order_id = orders.filtered('woo_store_id')[:1]

    def action_woo_refund(self):
        """ Refund this credit note in WooCommerce: its lines, and the money through the payment
        gateway when the store asks for it. """
        for move in self:
            if move.move_type != 'out_refund' or move.state != 'posted':
                raise UserError(_("Only a posted credit note is refunded in WooCommerce."))
            if move.woo_refund_id:
                raise UserError(_("%(move)s is already refunded in WooCommerce.", move=move.name))
            order = move.woo_order_id
            if not order:
                raise UserError(_("%(move)s is not the credit note of a WooCommerce order.", move=move.name))
            order.woo_store_id._connector_enqueue(
                '_connector_job_woo_refund', {'move_id': move.id}, model_name='account.move',
                name=_("Refund #%(number)s in WooCommerce (%(move)s)", number=order.woo_order_number, move=move.name),
                dedupe_key=f'refund:{move.id}', max_attempts=3)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': _("The refund is being sent to WooCommerce."), 'type': 'info'},
        }

    @api.model
    def _connector_job_woo_refund(self, job):
        move = self.browse(job.payload['move_id']).exists()
        if not move or move.woo_refund_id:
            return _("Nothing to refund")
        return move._woo_refund(job.backend)

    def _woo_refund(self, store):
        """ Create the refund of this credit note in WooCommerce. The taxes of each line are refunded
        in proportion of the quantity, as WooCommerce charged them. """
        self.ensure_one()
        order = self.woo_order_id
        data = store._woo_get(f'orders/{order.woo_order_id}') or {}
        items = {str(item['id']): item for key in ('line_items', 'shipping_lines', 'fee_lines')
                 for item in data.get(key) or []}
        refunded = defaultdict(lambda: {'qty': 0.0, 'total': 0.0})
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            woo_line = line.sale_line_ids[:1].woo_line_id
            if woo_line in items:
                refunded[woo_line]['qty'] += line.quantity
                refunded[woo_line]['total'] += line.price_subtotal
        line_items = []
        for woo_line, values in refunded.items():
            item = items[woo_line]
            ordered = float(item.get('quantity') or 1) or 1.0
            share = min(values['qty'] / ordered, 1.0) if item.get('quantity') else 1.0
            refund_line = {
                'id': int(woo_line),
                'refund_total': round(values['total'], 2),
                'refund_tax': [{'id': tax['id'], 'refund_total': round(float(tax.get('total') or 0) * share, 2)}
                               for tax in item.get('taxes') or [] if float(tax.get('total') or 0)],
            }
            if item.get('quantity'):
                refund_line['quantity'] = values['qty']
            line_items.append(refund_line)
        result = store._woo_post(f'orders/{order.woo_order_id}/refunds', {
            'amount': f'{self.amount_total:.2f}',
            'reason': self.ref or self.name,
            'line_items': line_items,
            'api_refund': store.refund_api,
            'restock_items': store.refund_restock,
        }) or {}
        self.write({'woo_refund_id': str(result.get('id') or ''), 'woo_store_id': store.id})
        if result.get('id'):
            order.woo_refund_ids = '\n'.join(filter(None, [order.woo_refund_ids, str(result['id'])]))
        return self
