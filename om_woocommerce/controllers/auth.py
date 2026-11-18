import json
import logging

from markupsafe import escape
from werkzeug.utils import redirect

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class OmWoocommerceAuth(http.Controller):
    """ Authorization of Odoo in WordPress (wc-auth): an administrator approves it, and WooCommerce
    sends a REST API key to Odoo. """

    def _error(self, message, status=400):
        body = f'<html><body style="font-family:sans-serif;padding:40px"><h2>WooCommerce</h2><p>{escape(message)}</p>' \
               f'<p><a href="/odoo/action-om_woocommerce.om_woocommerce_store_action">Back to the stores</a></p>' \
               f'</body></html>'
        return request.make_response(body, headers=[('Content-Type', 'text/html; charset=utf-8')], status=status)

    @http.route('/om_woocommerce/auth/start/<int:store_id>', type='http', auth='user', methods=['GET'])
    def start(self, store_id, **kwargs):
        store = request.env['om.woocommerce.store'].browse(store_id).exists()
        if not store or not request.env.user.has_group('om_woocommerce.group_om_woocommerce_manager'):
            return self._error(_("You are not allowed to connect this store."), status=403)
        store.check_access('write')
        return redirect(store._woo_authorize_url(), code=303, Response=None)

    @http.route('/om_woocommerce/auth/callback', type='http', auth='public', methods=['POST'], csrf=False,
                save_session=False)
    def callback(self, **kwargs):
        """ WooCommerce posts the key here (JSON), before it sends the administrator back. """
        try:
            data = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            data = dict(request.httprequest.form)
        if not isinstance(data, dict):
            return request.make_response('Bad Request', status=400)
        store = request.env['om.woocommerce.store']._woo_auth_callback(data)
        if not store:
            return request.make_response('Unknown authorization', status=403)
        return request.make_response('OK')

    @http.route('/om_woocommerce/auth/return/<int:store_id>', type='http', auth='user', methods=['GET'])
    def back(self, store_id, **params):
        store = request.env['om.woocommerce.store'].browse(store_id).exists()
        if not store or not request.env.user.has_group('om_woocommerce.group_om_woocommerce_manager'):
            return self._error(_("You are not allowed to connect this store."), status=403)
        try:
            store._woo_auth_return(params)
        except UserError as e:
            _logger.info("WooCommerce authorization of store %s: %s", store_id, e)
            return self._error(str(e))
        return redirect(f'/odoo/action-om_woocommerce.om_woocommerce_store_action/{store.id}', code=303,
                        Response=None)
