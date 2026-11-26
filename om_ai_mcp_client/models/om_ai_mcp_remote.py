import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
from datetime import timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_manifest
from odoo.tools import SQL

from .mcp_transport import (
    McpAuthRequired,
    McpClientError,
    McpHttpClient,
    McpRpcError,
    McpSessionExpired,
    parse_challenge,
)

_logger = logging.getLogger(__name__)

CALLBACK_PATH = '/om_ai_mcp_client/oauth/callback'
SECRET_FIELDS = ('bearer_token', 'oauth_client_secret', 'oauth_access_token', 'oauth_refresh_token',
                 'oauth_verifier', 'oauth_state_hash')
MAX_TOOLS = 500
MAX_RESULT_CHARS = 50000
STATE_MINUTES = 15
# MCP sessions of this worker: {(db, server id, url): (session id, protocol version)}
_SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()


def canonical_url(url):
    parts = urlsplit((url or '').strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query, ''))


class OmAiMcpRemote(models.Model):
    """An MCP server outside Odoo. Its tools become AI tools that the agents of
    the AI engine call over the Streamable HTTP transport."""
    _name = 'om.ai.mcp.remote'
    _description = 'Outside MCP Server'
    _order = 'sequence, name, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    url = fields.Char(string='Server URL', required=True, help='The MCP endpoint, e.g. https://example.com/mcp')
    tool_prefix = fields.Char(required=True, help='Put before the name of each tool given to the AI, so tools of '
                                                  'different servers never clash.')
    auth_type = fields.Selection([
        ('none', 'None'),
        ('bearer', 'Bearer token'),
        ('oauth', 'OAuth (sign in)'),
    ], string='Authentication', default='none', required=True)
    bearer_token = fields.Char(groups='om_ai.group_ai_manager', copy=False)
    bearer_token_input = fields.Char(string='Token', compute='_compute_secret_inputs', inverse='_inverse_bearer',
                                     groups='om_ai.group_ai_manager',
                                     help='Kept on the server and never sent back to the browser.')
    headers = fields.Text(string='Extra Headers', help='One header per line, e.g. X-Api-Version: 2')
    timeout = fields.Integer(string='Timeout (s)', default=30)
    group_ids = fields.Many2many('res.groups', string='Allowed Groups',
                                 help='Only users of these groups may use the tools of this server. Empty: every '
                                      'AI user.')
    state = fields.Selection([
        ('draft', 'Not Connected'),
        ('connected', 'Connected'),
        ('auth', 'Sign-In Needed'),
        ('error', 'Error'),
    ], default='draft', required=True, readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)
    last_connected = fields.Datetime(readonly=True, copy=False)
    server_name = fields.Char(readonly=True, copy=False)
    server_version = fields.Char(readonly=True, copy=False)
    protocol_version = fields.Char(readonly=True, copy=False)
    instructions = fields.Text(string='Server Instructions', readonly=True, copy=False)
    tool_ids = fields.One2many('om.ai.tool', 'mcp_remote_id', string='Tools',
                               context={'active_test': False})
    tool_count = fields.Integer(compute='_compute_tool_count', string='Tools Count')
    secret_set = fields.Boolean(string='Credentials Saved', compute='_compute_secret_set')

    # OAuth
    oauth_client_id = fields.Char(string='Client ID', copy=False,
                                  help='Leave empty: Odoo registers itself on servers that allow it.')
    oauth_client_secret = fields.Char(groups='om_ai.group_ai_manager', copy=False)
    oauth_client_secret_input = fields.Char(string='Client Secret', compute='_compute_secret_inputs',
                                            inverse='_inverse_client_secret', groups='om_ai.group_ai_manager')
    oauth_scope = fields.Char(string='Scopes', help='Leave empty to ask for the scopes the server announces.')
    oauth_issuer = fields.Char(string='Authorization Server', readonly=True, copy=False)
    oauth_authorize_url = fields.Char(readonly=True, copy=False)
    oauth_token_url = fields.Char(readonly=True, copy=False)
    oauth_revoke_url = fields.Char(readonly=True, copy=False)
    oauth_auth_method = fields.Char(readonly=True, copy=False, default='none')
    oauth_resource = fields.Char(readonly=True, copy=False)
    oauth_iss_check = fields.Boolean(readonly=True, copy=False)
    oauth_access_token = fields.Char(groups='om_ai.group_ai_manager', copy=False)
    oauth_refresh_token = fields.Char(groups='om_ai.group_ai_manager', copy=False)
    oauth_expires = fields.Datetime(string='Token Expires', readonly=True, copy=False)
    oauth_state_hash = fields.Char(groups='om_ai.group_ai_manager', copy=False)
    oauth_verifier = fields.Char(groups='om_ai.group_ai_manager', copy=False)
    oauth_state_expires = fields.Datetime(groups='om_ai.group_ai_manager', copy=False)
    oauth_signed_in = fields.Boolean(string='Signed In', compute='_compute_secret_set')

    _prefix_unique = models.Constraint('UNIQUE(tool_prefix)', 'Each server needs its own tool prefix.')
    _timeout_positive = models.Constraint('CHECK(timeout > 0)', 'The timeout must be positive.')

    def _has_field_access(self, field, operation):
        # secrets are only read by server code running as superuser
        if field.name in SECRET_FIELDS and operation == 'read' and not self.env.su:
            return False
        return super()._has_field_access(field, operation)

    def _compute_secret_inputs(self):
        self.bearer_token_input = False
        self.oauth_client_secret_input = False

    def _inverse_bearer(self):
        for server in self:
            if server.bearer_token_input:
                server.sudo().bearer_token = server.bearer_token_input.strip()

    def _inverse_client_secret(self):
        for server in self:
            if server.oauth_client_secret_input:
                server.sudo().oauth_client_secret = server.oauth_client_secret_input.strip()

    def _compute_secret_set(self):
        for server in self:
            sudo = server.sudo()
            server.secret_set = bool(sudo.bearer_token)
            server.oauth_signed_in = bool(sudo.oauth_access_token or sudo.oauth_refresh_token)

    def _compute_tool_count(self):
        counts = dict(self.env['om.ai.tool'].with_context(active_test=False)._read_group(
            [('mcp_remote_id', 'in', self.ids)], ['mcp_remote_id'], ['__count']))
        for server in self:
            server.tool_count = counts.get(server, 0)

    @api.onchange('name')
    def _onchange_name(self):
        if self.name and not self.tool_prefix:
            self.tool_prefix = re.sub(r'[^a-z0-9]+', '_', self.name.lower()).strip('_')[:20] or 'mcp'

    @api.constrains('url', 'tool_prefix', 'headers')
    def _check_definition(self):
        for server in self:
            parts = urlsplit(server.url or '')
            if parts.scheme not in ('http', 'https') or not parts.netloc:
                raise ValidationError(self.env._('The server URL must start with https:// or http://.'))
            if not re.match(r'^[A-Za-z][A-Za-z0-9_]{0,29}$', server.tool_prefix or ''):
                raise ValidationError(self.env._('The tool prefix must start with a letter and have only letters, '
                                                 'digits and underscores (30 at most).'))
            server._get_headers()

    def write(self, vals):
        if {'url', 'headers', 'auth_type'} & set(vals):
            self._forget_session()
        res = super().write(vals)
        if 'group_ids' in vals:
            for server in self:
                server.with_context(active_test=False).tool_ids.sudo().write(
                    {'group_ids': [fields.Command.set(server.group_ids.ids)]})
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_forget(self):
        self._forget_session()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def _get_headers(self):
        self.ensure_one()
        result = {}
        for line in (self.headers or '').splitlines():
            if not line.strip():
                continue
            name, sep, value = line.partition(':')
            name = name.strip()
            if not sep or not re.match(r'^[A-Za-z0-9-]+$', name) or '\r' in value or '\n' in value:
                raise ValidationError(self.env._('Write each extra header as "Name: value" on its own line.'))
            if name.lower() in ('mcp-session-id', 'mcp-protocol-version', 'content-type', 'accept'):
                raise ValidationError(self.env._('The header %s is set by Odoo.', name))
            result[name] = value.strip()
        return result

    def _session_key(self):
        return (self.env.cr.dbname, self.id, self.url)

    def _forget_session(self):
        with _SESSIONS_LOCK:
            for server in self:
                _SESSIONS.pop(server._session_key(), None)

    def _client_info(self):
        version = (get_manifest('om_ai_mcp_client') or {}).get('version', '1.0')
        return {'name': 'odoo-om-ai', 'title': 'Odoo AI', 'version': version}

    def _make_client(self, with_session=True):
        """A transport client with the credentials of the server (as superuser:
        the credentials are not readable otherwise)."""
        self.ensure_one()
        server = self.sudo()
        headers = server._get_headers()
        if server.auth_type == 'bearer' and server.bearer_token:
            headers['Authorization'] = 'Bearer %s' % server.bearer_token
        elif server.auth_type == 'oauth':
            token = server._oauth_valid_token()
            if token:
                headers['Authorization'] = 'Bearer %s' % token
        session_id, version = (None, None)
        if with_session:
            with _SESSIONS_LOCK:
                session_id, version = _SESSIONS.get(self._session_key(), (None, None))
        return McpHttpClient(server.url, headers=headers, timeout=server.timeout, session_id=session_id,
                             protocol_version=version, client_info=self._client_info())

    def _open_session(self, client):
        result = client.initialize()
        with _SESSIONS_LOCK:
            _SESSIONS[self._session_key()] = (client.session_id, client.protocol_version)
        return result

    def _mcp_request(self, method, params=None):
        """Send a request, opening a session first if needed. A session that
        ended is opened again once; an expired OAuth token is refreshed once."""
        self.ensure_one()
        for attempt in range(3):
            client = self._make_client()
            try:
                if not client.protocol_version:
                    self._open_session(client)
                return client.request(method, params)
            except McpSessionExpired:
                self._forget_session()
                if attempt:
                    raise
            except McpAuthRequired as error:
                self._forget_session()
                if self.auth_type == 'oauth' and attempt == 0 and self.sudo().oauth_refresh_token:
                    self._oauth_refresh(force=True)
                    continue
                raise UserError(self._auth_message(error)) from None
        raise UserError(self.env._('%s could not be reached.', self.name))

    def _auth_message(self, error):
        if self.auth_type == 'oauth':
            return self.env._('%s needs a new sign-in: an administrator can click Sign In on the server in '
                              'AI > Configuration > Outside MCP Servers.', self.name)
        return self.env._('%(server)s refused the credentials: %(error)s', server=self.name, error=error.message)

    def _error_text(self, error):
        if isinstance(error, McpRpcError):
            return self.env._('%(server)s answered an error: %(error)s', server=self.name, error=error.message)
        return self.env._('%(server)s: %(error)s', server=self.name, error=error.message)

    def action_connect(self):
        """Connect, read the server information and import its tools."""
        for server in self:
            values = {'last_connected': fields.Datetime.now()}
            try:
                server._forget_session()
                client = server._make_client(with_session=False)
                result = server._open_session(client)
                tools = server._list_tools()
            except UserError as error:
                server.write({'state': 'auth' if server.auth_type == 'oauth' else 'error',
                              'last_error': str(error.args[0])})
                continue
            except McpAuthRequired as error:
                server.write({'state': 'auth' if server.auth_type == 'oauth' else 'error',
                              'last_error': server._auth_message(error)})
                continue
            except McpClientError as error:
                server.write({'state': 'error', 'last_error': server._error_text(error)})
                continue
            info = result.get('serverInfo') or {}
            values.update({
                'state': 'connected',
                'last_error': False,
                'server_name': str(info.get('title') or info.get('name') or '')[:200],
                'server_version': str(info.get('version') or '')[:50],
                'protocol_version': client.protocol_version,
                'instructions': str(result.get('instructions') or '')[:5000] or False,
            })
            server.write(values)
            server._sync_tools(tools)
        return True

    def action_disconnect(self):
        for server in self:
            client = server._make_client()
            client.close()
            server._forget_session()
            server.sudo().write({'oauth_access_token': False, 'oauth_refresh_token': False, 'oauth_expires': False})
            server.write({'state': 'draft'})
        return True

    def _list_tools(self):
        tools, cursor = [], None
        for _page in range(50):
            params = {'cursor': cursor} if cursor else None
            try:
                result = self._mcp_request('tools/list', params) or {}
            except McpClientError as error:
                raise UserError(self._error_text(error)) from None
            tools.extend(item for item in result.get('tools') or [] if isinstance(item, dict) and item.get('name'))
            cursor = result.get('nextCursor')
            if not cursor or len(tools) >= MAX_TOOLS:
                break
        return tools[:MAX_TOOLS]

    def action_sync_tools(self):
        for server in self:
            server._sync_tools(server._list_tools())
        return True

    def _tool_code(self, name, taken):
        base = re.sub(r'[^A-Za-z0-9_]+', '_', '%s_%s' % (self.tool_prefix, name)).strip('_')
        code = base[:64]
        if code in taken:
            suffix = hashlib.sha1(name.encode()).hexdigest()[:6]
            code = '%s_%s' % (base[:57], suffix)
        return code

    def _sync_tools(self, remote_tools):
        """Create or update the AI tools of the server. The administrator's
        choices (enabled, read only, groups) are kept on update."""
        self.ensure_one()
        Tool = self.env['om.ai.tool'].sudo().with_context(active_test=False)
        existing = {tool.mcp_tool_name: tool for tool in Tool.search([('mcp_remote_id', '=', self.id)])}
        taken = set(Tool.search([('mcp_remote_id', '!=', self.id)]).mapped('code'))
        seen = set()
        for item in remote_tools:
            name = str(item['name'])[:200]
            if name in seen:
                continue
            seen.add(name)
            schema = item.get('inputSchema') if isinstance(item.get('inputSchema'), dict) else {}
            schema = dict(schema)
            schema.setdefault('type', 'object')
            schema.setdefault('properties', {})
            annotations = item.get('annotations') if isinstance(item.get('annotations'), dict) else {}
            values = {
                'name': str(item.get('title') or annotations.get('title') or name)[:200],
                'description': str(item.get('description') or name)[:4000],
                'parameters_schema': json.dumps(schema),
                'mcp_read_only_hint': bool(annotations.get('readOnlyHint')),
                'mcp_destructive_hint': annotations.get('destructiveHint', True) is not False
                and not annotations.get('readOnlyHint'),
            }
            tool = existing.get(name)
            if tool:
                tool.write(values)
                taken.add(tool.code)
                continue
            code = self._tool_code(name, taken)
            taken.add(code)
            values.update({
                'code': code,
                'mcp_remote_id': self.id,
                'mcp_tool_name': name,
                'method': '_ai_tool_mcp_call',
                'read_only': False,
                'active': True,
                'sequence': 500,
                'group_ids': [fields.Command.set(self.group_ids.ids)],
            })
            if 'mcp_enabled' in Tool._fields:
                # not offered again to the AI apps connected to Odoo
                values['mcp_enabled'] = False
            Tool.create(values)
        gone = [tool for name, tool in existing.items() if name not in seen]
        if gone:
            Tool.browse([tool.id for tool in gone]).unlink()
        return True

    def action_view_tools(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_ai.om_ai_tool_action')
        action.update({'domain': [('mcp_remote_id', '=', self.id)],
                       'context': {'active_test': False, 'default_mcp_remote_id': self.id}})
        return action

    def action_view_usage(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_ai.om_ai_usage_action')
        action.update({'domain': [('mcp_remote_id', '=', self.id)], 'context': {}, 'view_mode': 'list,form',
                       'views': [(False, 'list'), (False, 'form')]})
        return action

    # ------------------------------------------------------------------
    # Tool calls
    # ------------------------------------------------------------------
    def _user_allowed(self, user):
        self.ensure_one()
        return not self.group_ids or bool(self.group_ids & user.all_group_ids)

    def _mcp_call_tool(self, name, arguments):
        """Call a tool; return (is_error, text, structured content)."""
        self.ensure_one()
        try:
            result = self._mcp_request('tools/call', {'name': name, 'arguments': arguments or {}}) or {}
        except McpRpcError as error:
            return True, self._error_text(error), None
        except McpClientError as error:
            raise UserError(self._error_text(error)) from None
        parts = []
        for item in result.get('content') or []:
            if not isinstance(item, dict):
                continue
            kind = item.get('type')
            if kind == 'text':
                parts.append(str(item.get('text') or ''))
            elif kind == 'resource':
                resource = item.get('resource') or {}
                parts.append(str(resource.get('text') or '[file %s]' % resource.get('uri', '')))
            elif kind == 'resource_link':
                parts.append('[%s] %s' % (item.get('name') or 'link', item.get('uri') or ''))
            elif kind in ('image', 'audio'):
                parts.append('[%s %s not shown]' % (kind, item.get('mimeType') or ''))
        text = '\n'.join(parts)[:MAX_RESULT_CHARS]
        structured = result.get('structuredContent')
        if structured is not None and len(json.dumps(structured, default=str)) > MAX_RESULT_CHARS:
            structured = None
        return bool(result.get('isError')), text, structured

    # ------------------------------------------------------------------
    # OAuth (authorization code with PKCE, as an MCP client)
    # ------------------------------------------------------------------
    def _callback_url(self):
        return '%s%s' % (self.get_base_url().rstrip('/'), CALLBACK_PATH)

    def _http_json(self, method, url, **kwargs):
        try:
            response = requests.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as error:
            raise UserError(self.env._('%(url)s could not be reached: %(error)s', url=url,
                                       error=error.__class__.__name__)) from None
        try:
            data = response.json()
        except ValueError:
            data = None
        return response, data

    def _oauth_discover(self):
        """Find the authorization server from the 401 of the MCP server
        (protected resource metadata, RFC 9728), then its metadata (RFC 8414
        or OpenID Connect discovery)."""
        self.ensure_one()
        parts = urlsplit(self.url)
        origin = '%s://%s' % (parts.scheme, parts.netloc)
        challenge = {}
        try:
            probe = requests.post(self.url, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                'params': {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': self._client_info()}},
                headers=dict(self._get_headers(), Accept='application/json, text/event-stream'),
                timeout=self.timeout)
            if probe.status_code == 401:
                challenge = parse_challenge(probe.headers.get('WWW-Authenticate'))
            probe.close()
        except requests.exceptions.RequestException as error:
            raise UserError(self.env._('%(server)s could not be reached: %(error)s', server=self.name,
                                       error=error.__class__.__name__)) from None
        candidates = [challenge['resource_metadata']] if challenge.get('resource_metadata') else []
        path = parts.path.rstrip('/')
        if path:
            candidates.append('%s/.well-known/oauth-protected-resource%s' % (origin, path))
        candidates.append('%s/.well-known/oauth-protected-resource' % origin)
        metadata = None
        for candidate in candidates:
            response, data = self._http_json('GET', candidate)
            if response.status_code == 200 and isinstance(data, dict) and data.get('authorization_servers'):
                metadata = data
                break
        if not metadata:
            raise UserError(self.env._('%s does not announce an authorization server (no protected resource '
                                       'metadata).', self.name))
        resource = metadata.get('resource') or self.url
        # the metadata must be about this server
        if canonical_url(resource) != canonical_url(self.url) and not canonical_url(self.url).startswith(
                canonical_url(resource) + '/') and canonical_url(resource) != canonical_url(origin):
            raise UserError(self.env._('The protected resource metadata is about another server: %s', resource))
        issuer = str(metadata['authorization_servers'][0]).rstrip('/')
        scope = challenge.get('scope') or ' '.join(metadata.get('scopes_supported') or [])
        server_meta = self._oauth_server_metadata(issuer)
        if 'S256' not in (server_meta.get('code_challenge_methods_supported') or []):
            raise UserError(self.env._('The authorization server of %s does not support PKCE (S256): Odoo does not '
                                       'sign in without it.', self.name))
        return {
            'issuer': server_meta.get('issuer') or issuer,
            'resource': resource,
            'scope': scope,
            'metadata': server_meta,
        }

    def _oauth_server_metadata(self, issuer):
        parts = urlsplit(issuer)
        origin = '%s://%s' % (parts.scheme, parts.netloc)
        path = parts.path.rstrip('/')
        if path:
            urls = ['%s/.well-known/oauth-authorization-server%s' % (origin, path),
                    '%s/.well-known/openid-configuration%s' % (origin, path),
                    '%s%s/.well-known/openid-configuration' % (origin, path)]
        else:
            urls = ['%s/.well-known/oauth-authorization-server' % origin,
                    '%s/.well-known/openid-configuration' % origin]
        for url in urls:
            response, data = self._http_json('GET', url)
            if response.status_code == 200 and isinstance(data, dict) and data.get('authorization_endpoint') \
                    and data.get('token_endpoint'):
                if data.get('issuer') and data['issuer'].rstrip('/') != issuer:
                    raise UserError(self.env._('The authorization server metadata names another issuer: %s',
                                               data['issuer']))
                return data
        raise UserError(self.env._('The authorization server %s publishes no metadata.', issuer))

    def _oauth_register(self, metadata):
        """Dynamic client registration (RFC 7591) when no client ID is set."""
        endpoint = metadata.get('registration_endpoint')
        if not endpoint:
            raise UserError(self.env._('The authorization server of %s does not let apps register: enter the client '
                                       'ID (and secret) you got from its administrator.', self.name))
        response, data = self._http_json('POST', endpoint, json={
            'client_name': 'Odoo (%s)' % self.env.company.name,
            'redirect_uris': [self._callback_url()],
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'],
            'token_endpoint_auth_method': 'none',
            'software_id': 'om_ai_mcp_client',
            'software_version': self._client_info()['version'],
        })
        if response.status_code not in (200, 201) or not isinstance(data, dict) or not data.get('client_id'):
            raise UserError(self.env._('The registration of Odoo on the authorization server failed: %s',
                                       (data or {}).get('error_description') or (data or {}).get('error')
                                       or response.status_code))
        self.sudo().write({
            'oauth_client_id': data['client_id'],
            'oauth_client_secret': data.get('client_secret') or False,
            'oauth_auth_method': data.get('token_endpoint_auth_method') or 'none',
        })

    def action_oauth_sign_in(self):
        """Start the sign-in: the administrator is sent to the authorization
        server and comes back to the callback of this database."""
        self.ensure_one()
        if self.auth_type != 'oauth':
            raise UserError(self.env._('Choose OAuth as authentication first.'))
        found = self._oauth_discover()
        metadata = found['metadata']
        if not self.oauth_client_id:
            self._oauth_register(metadata)
        elif self.sudo().oauth_client_secret and self.oauth_auth_method == 'none':
            methods = metadata.get('token_endpoint_auth_methods_supported') or ['client_secret_basic']
            self.sudo().oauth_auth_method = 'client_secret_basic' if 'client_secret_basic' in methods \
                else 'client_secret_post'
        verifier = secrets.token_urlsafe(64)[:96]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        state = secrets.token_urlsafe(32)
        scope = self.oauth_scope or found['scope']
        self.sudo().write({
            'oauth_issuer': found['issuer'],
            'oauth_authorize_url': metadata['authorization_endpoint'],
            'oauth_token_url': metadata['token_endpoint'],
            'oauth_revoke_url': metadata.get('revocation_endpoint') or False,
            'oauth_resource': found['resource'],
            'oauth_iss_check': bool(metadata.get('authorization_response_iss_parameter_supported')),
            'oauth_state_hash': hashlib.sha256(state.encode()).hexdigest(),
            'oauth_verifier': verifier,
            'oauth_state_expires': fields.Datetime.now() + timedelta(minutes=STATE_MINUTES),
        })
        query = {
            'response_type': 'code',
            'client_id': self.oauth_client_id,
            'redirect_uri': self._callback_url(),
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'state': state,
            'resource': found['resource'],
        }
        if scope:
            query['scope'] = scope
        url = metadata['authorization_endpoint']
        return {
            'type': 'ir.actions.act_url',
            'url': '%s%s%s' % (url, '&' if '?' in url else '?', urlencode(query)),
            'target': 'self',
        }

    @api.model
    def _oauth_find_state(self, state):
        if not state or len(state) > 200:
            return self.browse()
        digest = hashlib.sha256(state.encode()).hexdigest()
        server = self.sudo().search([('oauth_state_hash', '=', digest)], limit=1)
        if not server or not hmac.compare_digest(server.oauth_state_hash or '', digest):
            return self.browse()
        if not server.oauth_state_expires or server.oauth_state_expires < fields.Datetime.now():
            return self.browse()
        return server

    def _oauth_client_auth(self, data):
        """Client authentication at the token endpoint; return requests kwargs."""
        server = self.sudo()
        data = dict(data, client_id=server.oauth_client_id)
        if server.oauth_client_secret:
            if server.oauth_auth_method == 'client_secret_post':
                data['client_secret'] = server.oauth_client_secret
            else:
                data.pop('client_id')
                return {'data': data, 'auth': (server.oauth_client_id, server.oauth_client_secret)}
        return {'data': data}

    def _oauth_store_tokens(self, data):
        if not isinstance(data, dict) or not data.get('access_token'):
            raise UserError(self.env._('The authorization server sent no access token.'))
        if str(data.get('token_type', 'bearer')).lower() != 'bearer':
            raise UserError(self.env._('The authorization server sent a token of an unknown type.'))
        expires_in = data.get('expires_in')
        values = {
            'oauth_access_token': data['access_token'],
            'oauth_expires': fields.Datetime.now() + timedelta(seconds=int(expires_in))
            if isinstance(expires_in, (int, float)) or str(expires_in or '').isdigit() else False,
        }
        if data.get('refresh_token'):
            values['oauth_refresh_token'] = data['refresh_token']
        self.sudo().write(values)

    def _oauth_finish(self, code, iss=None):
        """Exchange the code of the callback for tokens."""
        self.ensure_one()
        server = self.sudo()
        if server.oauth_iss_check and (not iss or iss.rstrip('/') != (server.oauth_issuer or '').rstrip('/')):
            raise UserError(self.env._('The answer came from another authorization server.'))
        verifier = server.oauth_verifier
        server.write({'oauth_state_hash': False, 'oauth_verifier': False, 'oauth_state_expires': False})
        kwargs = self._oauth_client_auth({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self._callback_url(),
            'code_verifier': verifier,
            'resource': server.oauth_resource,
        })
        response, data = self._http_json('POST', server.oauth_token_url, **kwargs)
        if response.status_code != 200:
            raise UserError(self.env._('The sign-in failed: %s', (data or {}).get('error_description') or
                                       (data or {}).get('error') or response.status_code))
        self._oauth_store_tokens(data)
        self._forget_session()
        self.action_connect()

    def _oauth_valid_token(self):
        """The access token, refreshed first when it expires within a minute."""
        server = self.sudo()
        if server.oauth_access_token and (not server.oauth_expires or
                                          server.oauth_expires > fields.Datetime.now() + timedelta(seconds=60)):
            return server.oauth_access_token
        if server.oauth_refresh_token:
            return self._oauth_refresh()
        return server.oauth_access_token

    def _oauth_refresh(self, force=False):
        """Refresh the access token in its own transaction, the server row
        locked, so two workers never use the same (rotated) refresh token."""
        self.ensure_one()
        old_token = self.sudo().oauth_access_token
        with self.env.registry.cursor() as cr:
            cr.execute(SQL("SET LOCAL lock_timeout = '15s'"))
            cr.execute(SQL('SELECT id FROM %s WHERE id = %s FOR UPDATE', SQL.identifier(self._table), self.id))
            server = self.env(cr=cr, su=True)[self._name].browse(self.id)
            if server.oauth_access_token and server.oauth_access_token != old_token and server.oauth_expires and \
                    server.oauth_expires > fields.Datetime.now() + timedelta(seconds=60):
                token = server.oauth_access_token  # another worker refreshed it
            elif not server.oauth_refresh_token:
                token = False
            else:
                kwargs = server._oauth_client_auth({
                    'grant_type': 'refresh_token',
                    'refresh_token': server.oauth_refresh_token,
                    'resource': server.oauth_resource,
                })
                response, data = server._http_json('POST', server.oauth_token_url, **kwargs)
                if response.status_code != 200:
                    _logger.info('MCP client: refresh of %s refused (%s)', server.name, response.status_code)
                    server.write({'oauth_access_token': False, 'oauth_refresh_token': False,
                                  'oauth_expires': False, 'state': 'auth',
                                  'last_error': self.env._('The sign-in expired: sign in again.')})
                    token = False
                else:
                    server._oauth_store_tokens(data)
                    token = server.oauth_access_token
        self.invalidate_recordset()
        if not token and force:
            raise UserError(self._auth_message(McpAuthRequired('')))
        return token

    def action_oauth_sign_out(self):
        for server in self:
            sudo = server.sudo()
            if sudo.oauth_revoke_url and sudo.oauth_refresh_token:
                try:
                    kwargs = server._oauth_client_auth({'token': sudo.oauth_refresh_token,
                                                        'token_type_hint': 'refresh_token'})
                    requests.post(sudo.oauth_revoke_url, timeout=server.timeout, **kwargs)
                except requests.exceptions.RequestException:
                    _logger.info('MCP client: could not revoke the token of %s', server.name)
            server._forget_session()
            sudo.write({'oauth_access_token': False, 'oauth_refresh_token': False, 'oauth_expires': False})
            server.write({'state': 'auth'})
        return True
