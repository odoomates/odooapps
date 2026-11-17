import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.om_connector_base.tools import verify_hmac_sha256

from ..tools.client import topic_to_enum

_logger = logging.getLogger(__name__)


class OmShopifyWebhook(http.Controller):
    """ Webhooks of the Shopify stores. A webhook is checked with the signature of Shopify, queued
    as a job, and answered at once: Shopify waits 5 seconds at most, then sends it again. """

    @http.route('/om_shopify/webhook/<int:store_id>', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def receive(self, store_id, **kwargs):
        headers = request.httprequest.headers
        body = request.httprequest.get_data()
        store = request.env['om.shopify.store'].sudo().browse(store_id).exists()
        if not store or not store.active:
            return request.make_response('Unknown store', status=404)
        if not verify_hmac_sha256(store.client_secret, body, headers.get('X-Shopify-Hmac-Sha256')):
            _logger.warning("Shopify webhook for store %s: wrong signature, ignored", store_id)
            return request.make_response('Wrong signature', status=401)
        shop_domain = (headers.get('X-Shopify-Shop-Domain') or '').lower()
        if shop_domain and shop_domain != store.shop_domain:
            _logger.warning("Shopify webhook for store %s sent by %s: ignored", store_id, shop_domain)
            return request.make_response('Wrong store', status=401)
        try:
            payload = json.loads(body or b'{}')
        except ValueError:
            return request.make_response('Bad Request', status=400)
        topic = topic_to_enum(headers.get('X-Shopify-Topic'))
        webhook_id = headers.get('X-Shopify-Webhook-Id') or headers.get('X-Shopify-Event-Id')
        store._shopify_receive_webhook(topic, payload, webhook_id)
        return request.make_response('OK')
