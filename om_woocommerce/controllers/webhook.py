import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.om_connector_base.tools import verify_hmac_sha256

_logger = logging.getLogger(__name__)


class OmWoocommerceWebhook(http.Controller):
    """ Webhooks of the WooCommerce stores. A webhook is checked with its signature, queued as a job,
    and answered at once: WooCommerce disables a webhook whose deliveries keep failing. """

    @http.route('/om_woocommerce/webhook/<int:store_id>', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def receive(self, store_id, **kwargs):
        headers = request.httprequest.headers
        body = request.httprequest.get_data()
        store = request.env['om.woocommerce.store'].sudo().browse(store_id).exists()
        if not store or not store.active:
            return request.make_response('Unknown store', status=404)
        signature = headers.get('X-WC-Webhook-Signature')
        if not signature and (body.startswith(b'webhook_id=') or request.httprequest.form.get('webhook_id')):
            # the ping WooCommerce sends when a webhook is created: unsigned, and answered OK
            return request.make_response('OK')
        if not verify_hmac_sha256(store.webhook_secret, body, signature):
            _logger.warning("WooCommerce webhook for store %s: wrong signature, ignored", store_id)
            return request.make_response('Wrong signature', status=401)
        try:
            payload = json.loads(body or b'{}')
        except ValueError:
            return request.make_response('Bad Request', status=400)
        if not isinstance(payload, dict):
            return request.make_response('Bad Request', status=400)
        store._woo_receive_webhook((headers.get('X-WC-Webhook-Topic') or '').strip().lower(), payload,
                                   headers.get('X-WC-Webhook-Delivery-ID'))
        return request.make_response('OK')
