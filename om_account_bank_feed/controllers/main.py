from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request


class BankFeedController(http.Controller):

    @http.route('/bank_feed/callback/<int:feed_id>/<string:token>', type='http', auth='user',
                methods=['GET'])
    def bank_feed_callback(self, feed_id, token, **params):
        """ The page the providers send the user back to, once the consent of the bank is given or refused.

        The token in the URL is random, single use and short lived: the page only accepts the user coming
        back from the consent this connection started, so a link from elsewhere cannot connect a bank.
        """
        connection = request.env['bank.feed.connection'].sudo().browse(feed_id).exists()
        if not connection or not connection._check_access_token(token):
            raise NotFound()
        user = request.env.user
        if connection.company_id not in user.company_ids or not user.has_group('account.group_account_manager'):
            raise Forbidden()
        connection = request.env['bank.feed.connection'].with_company(connection.company_id).browse(feed_id)
        connection._handle_callback(params)
        return request.redirect(
            f'/odoo/bank-feeds/{connection.id}')
