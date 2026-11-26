import psycopg2

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

# operation each built-in tool needs on its model
TOOL_OPERATIONS = {
    'create_records': 'create',
    'update_records': 'write',
    'delete_records': 'unlink',
    'post_message': 'write',
    'upload_attachment': 'write',
}
DESTRUCTIVE_TOOLS = ('update_records', 'delete_records')


class OmAiTool(models.Model):
    _inherit = 'om.ai.tool'

    mcp_enabled = fields.Boolean(string='Available to MCP Clients', default=True,
                                 help='Offer this tool to AI apps connected through the MCP server.')

    def _ai_mcp_context(self):
        return self.env.context.get('om_mcp_key_id') or self.env.context.get('om_mcp_grant_id')

    def _ai_check_operation(self, Model, operation):
        res = super()._ai_check_operation(Model, operation)
        if not self._ai_mcp_context():
            return res
        if operation != 'read' and self.env.context.get('om_mcp_read_only'):
            raise AccessError(self.env._('This MCP key is read only.'))
        if not self.env['om.mcp.model.access']._allows(Model._name, operation):
            raise AccessError(self.env._('MCP clients may not %(operation)s "%(model)s". An administrator can '
                                         'allow it in AI > MCP Server > Model Permissions.',
                                         operation=operation, model=Model._name))
        return res

    @api.model
    def _ai_batch_limit(self):
        if self._ai_mcp_context():
            return max(1, self.env['ir.config_parameter'].sudo().get_int('om_ai_mcp.batch_limit', 20))
        return super()._ai_batch_limit()

    # ------------------------------------------------------------------
    # MCP registry
    # ------------------------------------------------------------------
    def _mcp_operation(self):
        self.ensure_one()
        tool = self.sudo()
        if tool.server_action_id:
            return 'method'
        if tool.code in TOOL_OPERATIONS:
            return TOOL_OPERATIONS[tool.code]
        return 'read' if tool.read_only else 'method'

    @api.model
    def _mcp_get_tools(self, read_only=False):
        """Tools offered to the current MCP user: the tools of the registry the user
        may use, minus the write tools of read-only keys and the tools that no model
        permission allows."""
        tools = self._get_available().sudo().filtered('mcp_enabled')
        if read_only:
            tools = tools.filtered('read_only')
        permissions = self.env['om.mcp.model.access']._get_permissions()
        result = self.browse()
        for tool in tools:
            operation = tool._mcp_operation()
            if tool.server_action_id:
                model_name = tool.server_action_id.model_id.model
                if model_name and 'method' not in permissions.get(model_name, ()):
                    continue
            elif operation != 'read':
                models_allowed = [name for name, ops in permissions.items() if operation in ops]
                if tool.model_ids:
                    models_allowed = [name for name in models_allowed if name in tool.model_ids.mapped('model')]
                if not models_allowed:
                    continue
            result |= tool
        return result.with_env(self.env)

    def _mcp_spec(self, protocol_version):
        """Tool definitions in the MCP format."""
        result = []
        for tool in self.sudo():
            schema = tool._get_parameters()
            schema.setdefault('type', 'object')
            spec = {
                'name': tool.code,
                'description': tool.description,
                'inputSchema': schema,
            }
            if protocol_version >= '2025-03-26':
                spec['annotations'] = {
                    'title': tool.name,
                    'readOnlyHint': bool(tool.read_only),
                    'destructiveHint': not tool.read_only and (
                        tool.code in DESTRUCTIVE_TOOLS or bool(tool.server_action_id)),
                    'idempotentHint': bool(tool.read_only),
                    'openWorldHint': False,
                }
            if protocol_version >= '2025-06-18':
                spec['title'] = tool.name
            result.append(spec)
        return result

    def _mcp_execute(self, arguments):
        """Run the tool as the current user. Return (status, result)."""
        self.ensure_one()
        tool = self.sudo()
        if not hasattr(type(self), tool.method) or not tool.method.startswith('_ai_tool_'):
            return 'tool_error', {'error': 'Unknown tool method.'}
        try:
            with self.env.cr.savepoint():
                return 'success', getattr(self.with_env(self.env), tool.method)(tool, **arguments)
        except AccessError as error:
            return 'denied', {'error': str(error.args[0] if error.args else error)}
        except (MissingError, UserError, ValidationError, ValueError, TypeError, KeyError) as error:
            return 'tool_error', {'error': str(error.args[0] if error.args else error)}
        except psycopg2.IntegrityError as error:
            return 'tool_error', {'error': self._ai_integrity_message(error)}
