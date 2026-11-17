import logging

from markupsafe import escape
from werkzeug.utils import redirect

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from ..tools.client import ShopifyClient, is_valid_shop_domain, normalize_shop_domain

_logger = logging.getLogger(__name__)


class OmShopifyOAuth(http.Controller):
    """ Installation of the app on a store by the merchant (OAuth authorization code grant). """

    def _error(self, message, status=400):
        body = f'<html><body style="font-family:sans-serif;padding:40px"><h2>Shopify</h2><p>{escape(message)}</p>' \
               f'<p><a href="/odoo/action-om_shopify.om_shopify_store_action">Back to the stores</a></p></body></html>'
        return request.make_response(body, headers=[('Content-Type', 'text/html; charset=utf-8')], status=status)

    @http.route('/om_shopify/oauth/start/<int:store_id>', type='http', auth='user', methods=['GET'])
    def start(self, store_id, **kwargs):
        store = request.env['om.shopify.store'].browse(store_id).exists()
        if not store or not request.env.user.has_group('om_shopify.group_om_shopify_manager'):
            return self._error(_("You are not allowed to connect this store."), status=403)
        store.check_access('write')
        try:
            url = store._shopify_oauth_authorize_url()
        except UserError as e:
            return self._error(str(e))
        return redirect(url, code=303, Response=None)

    @http.route('/om_shopify/oauth/install', type='http', auth='user', methods=['GET'])
    def install(self, **params):
        """ The App URL: Shopify sends the merchant here when the app is installed from Shopify. """
        shop = normalize_shop_domain(params.get('shop'))
        if not is_valid_shop_domain(shop):
            return self._error(_("Unknown store."), status=404)
        store = request.env['om.shopify.store'].search([('shop_domain', '=', shop), ('auth_type', '=', 'oauth')],
                                                       limit=1)
        if not store or not ShopifyClient.verify_oauth_query(store.sudo().client_secret, params):
            return self._error(_("No store of Odoo installs the app on %(shop)s.", shop=shop), status=404)
        if store.sudo().access_token and store.state == 'connected':
            return redirect(f'/odoo/action-om_shopify.om_shopify_store_action/{store.id}', code=303, Response=None)
        return self.start(store.id)

    @http.route('/om_shopify/oauth/callback', type='http', auth='user', methods=['GET'])
    def callback(self, **params):
        store = request.env['om.shopify.store']._shopify_oauth_store_of_state(params.get('state'))
        if not store:
            return self._error(_("This installation is unknown or already done: start it again from the store."),
                               status=403)
        if params.get('error'):
            return self._error(_("Shopify refused the installation: %(error)s", error=params.get('error_description')
                                 or params['error']), status=403)
        try:
            store.with_user(request.env.user)._shopify_oauth_complete(params)
        except UserError as e:
            _logger.warning("Shopify OAuth callback for store %s refused: %s", store.id, e)
            return self._error(str(e), status=403)
        return redirect(f'/odoo/action-om_shopify.om_shopify_store_action/{store.id}', code=303, Response=None)
