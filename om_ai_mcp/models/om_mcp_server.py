import json

from odoo import api, models
from odoo.modules.module import get_manifest


PROTOCOL_VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
LATEST_VERSION = PROTOCOL_VERSIONS[0]
DEFAULT_VERSION = '2025-03-26'

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

INSTRUCTIONS = (
    'Tools to work with Odoo records as the user who owns the key. '
    'Use find_models and model_fields to learn the model and field names first. '
    'Filters are lists of {field, operator, value} combined with AND. '
    'Tools that change data act at once: ask the user before you create, update or delete records.'
)


class McpError(Exception):
    """A JSON-RPC error to send back to the client."""

    def __init__(self, code, message, data=None, status='error'):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.status = status


class OmMcpServer(models.AbstractModel):
    """The MCP protocol on top of the om_ai tool registry. The methods run in
    the environment of the user who owns the key (never as superuser)."""
    _name = 'om.mcp.server'
    _description = 'MCP Server'

    @api.model
    def _mcp_server_info(self):
        version = (get_manifest('om_ai_mcp') or {}).get('version', '1.0')
        return {'name': 'odoo-mcp', 'title': 'Odoo', 'version': version}

    @api.model
    def _mcp_instructions(self):
        extra = self.env['ir.config_parameter'].sudo().get_str('om_ai_mcp.instructions')
        return ('%s %s' % (INSTRUCTIONS, extra)).strip()

    @api.model
    def _mcp_capabilities(self):
        return {'tools': {'listChanged': False}}

    @api.model
    def _mcp_negotiate(self, requested):
        return requested if requested in PROTOCOL_VERSIONS else LATEST_VERSION

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------
    @api.model
    def _mcp_dispatch(self, method, params, info):
        """Answer one JSON-RPC request. ``info`` is a dict shared with the
        controller: protocol_version, read_only, and the log values (tool, model,
        status, error) are put in it."""
        if params is not None and not isinstance(params, dict):
            raise McpError(INVALID_PARAMS, 'params must be an object')
        params = params or {}
        if method == 'initialize':
            return self._mcp_initialize(params, info)
        if method == 'ping':
            return {}
        if method == 'tools/list':
            return self._mcp_tools_list(params, info)
        if method == 'tools/call':
            return self._mcp_tools_call(params, info)
        raise McpError(METHOD_NOT_FOUND, 'Method not found: %s' % method)

    @api.model
    def _mcp_initialize(self, params, info):
        requested = params.get('protocolVersion')
        if not isinstance(requested, str):
            raise McpError(INVALID_PARAMS, 'protocolVersion is required')
        version = self._mcp_negotiate(requested)
        info['protocol_version'] = version
        client = params.get('clientInfo') or {}
        if isinstance(client, dict):
            info['client_name'] = str(client.get('name') or '')[:100]
            info['client_version'] = str(client.get('version') or '')[:50]
        result = {
            'protocolVersion': version,
            'capabilities': self._mcp_capabilities(),
            'serverInfo': self._mcp_server_info(),
            'instructions': self._mcp_instructions(),
        }
        if version < '2025-06-18':
            result['serverInfo'].pop('title', None)
        return result

    @api.model
    def _mcp_tools_list(self, params, info):
        tools = self.env['om.ai.tool']._mcp_get_tools(read_only=info.get('read_only'))
        return {'tools': tools._mcp_spec(info['protocol_version'])}

    @api.model
    def _mcp_tools_call(self, params, info):
        name = params.get('name')
        arguments = params.get('arguments')
        if not isinstance(name, str) or not name:
            raise McpError(INVALID_PARAMS, 'name is required')
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise McpError(INVALID_PARAMS, 'arguments must be an object')
        info['tool'] = name[:100]
        if isinstance(arguments.get('model'), str):
            info['model'] = arguments['model'][:100]
        Tool = self.env['om.ai.tool']
        tool = Tool._mcp_get_tools(read_only=info.get('read_only')).filtered(lambda t: t.code == name)
        if not tool:
            # a write tool asked with a read-only key, or a tool the user may not use
            hidden = Tool._get_available(codes=[name]).sudo().filtered('mcp_enabled')
            if hidden:
                info['status'] = 'denied'
                message = self.env._('This MCP key is read only.') \
                    if info.get('read_only') and not hidden.read_only \
                    else self.env._('This tool is not allowed for MCP clients: no model permission allows it.')
                info['error'] = message
                return self._mcp_content({'error': message}, info, is_error=True)
            raise McpError(INVALID_PARAMS, 'Unknown tool: %s' % name, status='denied')
        if tool.sudo().server_action_id.model_id:
            info['model'] = tool.sudo().server_action_id.model_id.model
        schema = tool._get_parameters()
        properties = schema.get('properties') or {}
        missing = [key for key in schema.get('required') or [] if key not in arguments]
        unknown = [key for key in arguments if key not in properties] \
            if properties and not tool.sudo().server_action_id else []
        if missing or unknown:
            message = '; '.join(filter(None, [
                missing and 'Missing arguments: %s' % ', '.join(missing),
                unknown and 'Unknown arguments: %s' % ', '.join(unknown),
            ]))
            info.update(status='tool_error', error=message)
            return self._mcp_content({'error': message}, info, is_error=True)
        status, result = tool._mcp_execute(arguments)
        if status != 'success':
            info.update(status=status, error=result.get('error'))
        return self._mcp_content(result, info, is_error=status != 'success')

    @api.model
    def _mcp_content(self, result, info, is_error=False):
        """Tool output as MCP content: the JSON as text, images as image content,
        and the structured content for the clients that know it."""
        content = []
        images = []
        if isinstance(result, dict) and isinstance(result.get('image'), dict):
            result = dict(result)
            image = result.pop('image')
            images.append({'type': 'image', 'data': image.get('data') or '',
                           'mimeType': image.get('mime_type') or 'image/png'})
        if is_error and isinstance(result, dict) and set(result) == {'error'}:
            text = str(result['error'])
        else:
            text = json.dumps(result, ensure_ascii=False, default=str)
        content.append({'type': 'text', 'text': text})
        content.extend(images)
        answer = {'content': content, 'isError': bool(is_error)}
        if not is_error and isinstance(result, dict) and info.get('protocol_version', DEFAULT_VERSION) >= '2025-06-18':
            answer['structuredContent'] = json.loads(json.dumps(result, default=str))
        return answer

