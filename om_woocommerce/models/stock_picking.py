from odoo import _, api, fields, models

TRACKING_NAMESPACE = 'wc-shipment-tracking/v3'


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    woo_completed = fields.Boolean(string='Completed in WooCommerce', readonly=True, copy=False)

    def _action_done(self):
        res = super()._action_done()
        orders = self.filtered(lambda p: p.picking_type_code == 'outgoing').sale_id.filtered('woo_store_id')
        orders._woo_invoice_delivered()
        if self.env.context.get('om_woocommerce_no_complete'):
            return res
        for order in orders:
            store = order.woo_store_id
            open_deliveries = order.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing' and p.state not in ('done', 'cancel'))
            if store.fulfillment_push and not open_deliveries:
                store._connector_enqueue(
                    '_connector_job_woo_complete', {'order_id': order.id}, model_name='stock.picking',
                    name=_("Complete #%(number)s", number=order.woo_order_number),
                    dedupe_key=f'complete:{order.id}')
        return res

    @api.model
    def _connector_job_woo_complete(self, job):
        order = self.env['sale.order'].browse(job.payload['order_id']).exists()
        if not order or not order.woo_order_id:
            return _("Nothing to complete")
        return self._woo_complete(job.backend, order)

    @api.model
    def _woo_complete(self, store, order):
        """ Send the tracking numbers of the deliveries of ``order``, then complete it in WooCommerce
        (which emails the customer). Gives the deliveries. """
        pickings = order.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state == 'done'
                                              and not p.woo_completed)
        path = f'orders/{order.woo_order_id}'
        for picking in pickings.filtered('carrier_tracking_ref'):
            if store.fulfillment_tracking == 'plugin':
                sent = store._woo_client().post(f'{path}/shipment-trackings', {
                    'custom_tracking_provider': picking.carrier_id.name or _("Carrier"),
                    'tracking_number': picking.carrier_tracking_ref,
                    'custom_tracking_link': picking._woo_tracking_url() or '',
                    'date_shipped': fields.Date.to_string(fields.Date.context_today(picking, picking.date_done)),
                }, namespace=TRACKING_NAMESPACE)
                if sent is None:
                    order.message_post(body=_("The WooCommerce Shipment Tracking extension is not active on %(store)s: "
                                              "the tracking number is sent as a note.", store=store.name))
                    picking._woo_tracking_note(store, path)
            elif store.fulfillment_tracking == 'note':
                picking._woo_tracking_note(store, path)
        if order.woo_status != 'completed':
            data = store._woo_put(path, {'status': 'completed'}) or {}
            order.woo_status = data.get('status') or 'completed'
        pickings.woo_completed = True
        return pickings

    def _woo_tracking_url(self):
        self.ensure_one()
        return self.carrier_tracking_url if 'carrier_tracking_url' in self._fields else False

    def _woo_tracking_note(self, store, path):
        self.ensure_one()
        url = self._woo_tracking_url()
        note = _("Your order was shipped with %(carrier)s, tracking number %(number)s.",
                 carrier=self.carrier_id.name or _("the carrier"), number=self.carrier_tracking_ref)
        if url:
            note += f' {url}'
        store._woo_post(f'{path}/notes', {'note': note, 'customer_note': True})
