import json
import time

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

MAX_LOG_TEXT = 20000


class OmAiTool(models.Model):
    _inherit = 'om.ai.tool'

    mcp_remote_id = fields.Many2one('om.ai.mcp.remote', string='Outside MCP Server', ondelete='cascade',
                                    index='btree_not_null', readonly=True)
    mcp_tool_name = fields.Char(string='Tool Name on the Server', readonly=True)
    mcp_read_only_hint = fields.Boolean(string='Read-Only Hint', readonly=True,
                                        help='The server announces that the tool does not change anything. Odoo '
                                             'does not trust it: an administrator decides with Read Only.')
    mcp_destructive_hint = fields.Boolean(string='Destructive Hint', readonly=True)

    def _ai_tool_mcp_call(self, tool, **arguments):
        """Call the tool on its outside MCP server. Runs for the current user,
        who must be allowed by the groups of the server."""
        remote = tool.sudo().mcp_remote_id
        if not remote or not remote.active:
            raise UserError(self.env._('The MCP server of this tool is not available.'))
        if not remote._user_allowed(self.env.user):
            raise AccessError(self.env._('You may not use the tools of %s.', remote.name))
        company = self.env.company.sudo()
        log = {'feature': 'mcp_client', 'mcp_remote_id': remote.id, 'mcp_tool': tool.code}
        if company.om_ai_log_content:
            log['request_text'] = json.dumps(arguments, ensure_ascii=False, default=str)[:MAX_LOG_TEXT]
        started = time.monotonic()
        try:
            is_error, text, structured = remote._mcp_call_tool(tool.sudo().mcp_tool_name, arguments)
        except UserError as error:
            log.update(status='error', error=str(error.args[0]), duration=time.monotonic() - started)
            self.env['om.ai']._ai_log(log, separate=True)
            raise
        log['duration'] = time.monotonic() - started
        if company.om_ai_log_content:
            log['response_text'] = text[:MAX_LOG_TEXT]
        if is_error:
            log.update(status='error', error=text[:2000] or 'Tool error')
            self.env['om.ai']._ai_log(log)
            return {'error': text or self.env._('The tool failed.')}
        self.env['om.ai']._ai_log(log)
        result = {'result': text}
        if structured is not None:
            result['structured'] = structured
        return result
