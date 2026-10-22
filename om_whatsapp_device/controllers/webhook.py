import hashlib
import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

from odoo.addons.om_whatsapp_device.models.om_whatsapp_account import WEBHOOK_PATH

_logger = logging.getLogger(__name__)


class OmWhatsappDeviceWebhook(http.Controller):
    """ What the WhatsApp Bridge reads from WhatsApp: the state of a session,
    messages, the status of the ones sent, reactions; signed with the secret
    of the bridge. The bridge names the database (X-Odoo-Database). """

    @http.route(WEBHOOK_PATH, type='http', auth='public', methods=['POST'], csrf=False)
    def receive(self):
        body = request.httprequest.get_data()
        env = request.env(user=SUPERUSER_ID)
        Account = env['om.whatsapp.account'].with_context(active_test=False)
        secret = Account._device_bridge_secret().encode()
        expected = 'sha256=' + hmac.new(secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, request.httprequest.headers.get('X-Signature-256', '')):
            _logger.warning("WhatsApp Bridge: a call not signed with its secret, ignored")
            return request.make_response('Forbidden', status=403)
        try:
            payload = json.loads(body)
        except ValueError:
            return request.make_response('Bad Request', status=400)
        account = Account.search([('provider', '=', 'device'), ('device_key', '=', payload.get('key'))], limit=1)
        if not account:
            return request.make_response('Not Found', status=404)
        for item in payload.get('items') or []:
            try:
                with env.cr.savepoint():
                    if item.get('kind') == 'state':
                        account._device_write_state(item)
                    else:
                        account._om_whatsapp_receive_item(item)
            except Exception:
                _logger.exception("WhatsApp Bridge: %s %s of %s not recorded", item.get('kind'), item.get('id'), account.name)
        return request.make_response('OK')
