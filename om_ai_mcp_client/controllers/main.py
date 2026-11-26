import logging

from odoo.exceptions import UserError
from odoo.http import Controller, request, route

from odoo.addons.om_ai_mcp_client.models.om_ai_mcp_remote import CALLBACK_PATH

_logger = logging.getLogger(__name__)


class OmAiMcpClientController(Controller):

    @route(CALLBACK_PATH, type='http', auth='user', methods=['GET'], sitemap=False)
    def oauth_callback(self, state=None, code=None, error=None, error_description=None, iss=None, **kwargs):
        """The authorization server sends the administrator back here."""
        if not request.env.user.has_group('om_ai.group_ai_manager'):
            return request.not_found()
        Remote = request.env['om.ai.mcp.remote']
        server = Remote._oauth_find_state(state)
        if not server:
            return request.redirect('/odoo/ai-mcp-servers')
        target = '/odoo/ai-mcp-servers/%s' % server.id
        if error or not code:
            server.sudo().write({'oauth_state_hash': False, 'oauth_verifier': False, 'oauth_state_expires': False,
                                 'state': 'auth',
                                 'last_error': request.env._('The sign-in was refused: %s',
                                                             error_description or error or 'no code')})
            return request.redirect(target)
        try:
            server._oauth_finish(code, iss)
        except UserError as exc:
            _logger.info('MCP client: sign-in to %s failed', server.name)
            server.sudo().write({'state': 'auth', 'last_error': str(exc.args[0])})
        return request.redirect(target)
