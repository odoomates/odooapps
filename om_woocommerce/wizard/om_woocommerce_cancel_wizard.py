from odoo import _, fields, models


class OmWoocommerceCancelWizard(models.TransientModel):
    _name = 'om.woocommerce.cancel.wizard'
    _description = 'Cancel a WooCommerce Order'

    order_id = fields.Many2one('sale.order', required=True)
    note = fields.Char(help="Added as a private note to the order in WooCommerce.")

    def action_cancel(self):
        self.ensure_one()
        order = self.order_id
        store = order.woo_store_id
        path = f'orders/{order.woo_order_id}'
        if self.note:
            store._woo_post(f'{path}/notes', {'note': self.note, 'customer_note': False})
        data = store._woo_put(path, {'status': 'cancelled'}) or {}
        order.woo_status = data.get('status') or 'cancelled'
        order.message_post(body=_("Cancelled in WooCommerce. A paid order is refunded there, by a refund of its own."))
        order._woo_cancel(data)
        return {'type': 'ir.actions.act_window_close'}
