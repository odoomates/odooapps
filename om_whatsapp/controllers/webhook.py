import hashlib
import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

from odoo.addons.om_whatsapp.models.om_whatsapp_account import WEBHOOK_PATH

_logger = logging.getLogger(__name__)


class OmWhatsappWebhook(http.Controller):
    """ The webhook of the Meta app: Meta checks it with the verify token,
    then posts the messages, statuses and template updates of the business
    accounts, signed with the App Secret. """

    @http.route(WEBHOOK_PATH, type='http', auth='public', methods=['GET'], csrf=False)
    def verify(self, **params):
        accounts = request.env['om.whatsapp.account'].sudo().search([('provider', '=', 'meta')])
        token = params.get('hub.verify_token')
        if params.get('hub.mode') == 'subscribe' and token and token in accounts.mapped('meta_verify_token'):
            return request.make_response(params.get('hub.challenge', ''), headers=[('Content-Type', 'text/plain')])
        return request.make_response('Forbidden', status=403)

    @http.route(WEBHOOK_PATH, type='http', auth='public', methods=['POST'], csrf=False)
    def receive(self):
        body = request.httprequest.get_data()
        try:
            payload = json.loads(body)
        except ValueError:
            return request.make_response('Bad Request', status=400)
        env = request.env(user=SUPERUSER_ID)
        Account = env['om.whatsapp.account'].with_context(active_test=False)
        signature = request.httprequest.headers.get('X-Hub-Signature-256', '')
        for entry in payload.get('entry') or []:
            for change in entry.get('changes') or []:
                value = change.get('value') or {}
                phone_number_id = (value.get('metadata') or {}).get('phone_number_id')
                account = Account.search([('provider', '=', 'meta'), ('meta_phone_number_id', '=', phone_number_id)], limit=1) \
                    if phone_number_id else Account.search([('provider', '=', 'meta'), ('meta_waba_id', '=', entry.get('id'))], limit=1)
                if not account:
                    continue
                if not self._signed_by(account, body, signature):
                    _logger.warning("WhatsApp webhook not signed by the app of %s: ignored", account.name)
                    return request.make_response('Forbidden', status=403)
                try:
                    with env.cr.savepoint():
                        account._meta_process_webhook(change.get('field'), value)
                except Exception:
                    # an answer other than 200 makes Meta send it again and again
                    _logger.exception("WhatsApp webhook of %s not processed", account.name)
        return request.make_response('OK')

    @staticmethod
    def _signed_by(account, body, signature):
        secret = (account.meta_app_secret or '').encode()
        expected = 'sha256=' + hmac.new(secret, body, hashlib.sha256).hexdigest()
        return bool(secret) and hmac.compare_digest(expected, signature)
