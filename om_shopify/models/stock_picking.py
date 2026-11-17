import logging
from collections import defaultdict

from odoo import _, api, fields, models

from ..tools import queries

_logger = logging.getLogger(__name__)

OPEN_FULFILLMENT_STATUSES = ('OPEN', 'IN_PROGRESS')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    shopify_fulfillment_gid = fields.Char(string='Shopify Fulfillment', readonly=True, copy=False)

    def _action_done(self):
        res = super()._action_done()
        self.filtered(lambda p: p.picking_type_code == 'outgoing').sale_id.filtered(
            'shopify_store_id')._shopify_invoice_delivered()
        if self.env.context.get('om_shopify_no_fulfill'):
            return res
        for picking in self:
            order = picking.sale_id
            if picking.picking_type_code == 'outgoing' and order.shopify_store_id and order.shopify_store_id.fulfillment_push:
                order.shopify_store_id._connector_enqueue(
                    '_connector_job_shopify_fulfill', {'picking_id': picking.id}, model_name='stock.picking',
                    name=_("Fulfill %(order)s (%(picking)s)", order=order.shopify_order_name, picking=picking.name),
                    dedupe_key=f'fulfill:{picking.id}')
        return res

    @api.model
    def _connector_job_shopify_fulfill(self, job):
        picking = self.browse(job.payload['picking_id']).exists()
        if not picking or picking.state != 'done':
            return _("Nothing to fulfill")
        return picking._shopify_fulfill(job.backend)

    def _shopify_fulfill(self, store):
        """ Tell Shopify that the delivered products of this picking are fulfilled, with the tracking
        number. Gives the picking. """
        self.ensure_one()
        order = self.sale_id
        quantities = defaultdict(float)
        for move in self.move_ids.filtered(lambda m: m.state == 'done' and m.sale_line_id.shopify_line_gid):
            quantities[move.sale_line_id.shopify_line_gid] += move.uom_id._compute_quantity(
                move.quantity, move.sale_line_id.product_uom_id)
        if not quantities:
            return _("No Shopify line in this picking")
        data = store._shopify_execute(queries.FULFILLMENT_ORDERS, {'id': order.shopify_order_gid}).get('order') or {}
        by_location = defaultdict(list)
        for fulfillment_order in (data.get('fulfillmentOrders') or {}).get('nodes') or []:
            if fulfillment_order.get('status') not in OPEN_FULFILLMENT_STATUSES:
                continue
            items = []
            for line in (fulfillment_order.get('lineItems') or {}).get('nodes') or []:
                line_gid = (line.get('lineItem') or {}).get('id')
                quantity = min(int(quantities.get(line_gid, 0)), line.get('remainingQuantity') or 0)
                if quantity > 0:
                    items.append({'id': line['id'], 'quantity': quantity})
                    quantities[line_gid] -= quantity
            if items:
                location = ((fulfillment_order.get('assignedLocation') or {}).get('location') or {}).get('id')
                by_location[location].append({'fulfillmentOrderId': fulfillment_order['id'],
                                              'fulfillmentOrderLineItems': items})
        if not by_location:
            return _("Already fulfilled in Shopify")
        tracking = self._shopify_tracking_info()
        gids = []
        for line_items in by_location.values():
            fulfillment = {'lineItemsByFulfillmentOrder': line_items, 'notifyCustomer': store.fulfillment_notify}
            if tracking:
                fulfillment['trackingInfo'] = tracking
            result = store._shopify_mutate(queries.FULFILLMENT_CREATE, {'fulfillment': fulfillment}, 'fulfillmentCreate')
            gids.append((result.get('fulfillment') or {}).get('id'))
        self.shopify_fulfillment_gid = ', '.join(filter(None, gids))
        return self

    def _shopify_tracking_info(self):
        self.ensure_one()
        if not self.carrier_tracking_ref:
            return {}
        info = {'number': self.carrier_tracking_ref}
        if self.carrier_id:
            info['company'] = self.carrier_id.name
        url = self.carrier_tracking_url if 'carrier_tracking_url' in self._fields else False
        if url:
            info['url'] = url
        return info
