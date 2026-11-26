import json
import logging
import re
import secrets
import time
from urllib.parse import urlsplit

import psycopg2

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import ConcurrencyError
from odoo.http import Controller, request, route

from odoo.addons.om_ai_mcp.controllers.oauth import canonical_uri, mcp_resource_url, resource_metadata_url
from odoo.addons.om_ai_mcp.models.om_mcp_oauth import ACCESS_PREFIX, KEY_SCOPES, SCOPE_WRITE
from odoo.addons.om_ai_mcp.models.om_mcp_server import (
    DEFAULT_VERSION,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    PARSE_ERROR,
    PROTOCOL_VERSIONS,
    McpError,
)

_logger = logging.getLogger(__name__)

SESSION_HEADER = 'Mcp-Session-Id'
VERSION_HEADER = 'MCP-Protocol-Version'
CORS_HEADERS = ', '.join([
    'Authorization', 'Content-Type', 'Accept', SESSION_HEADER, VERSION_HEADER, 'Last-Event-ID', 'X-Odoo-Database',
])
SESSION_TOUCH_SECONDS = 300


class OmMcpController(Controller):
    """The MCP endpoint (Streamable HTTP transport). Every request needs an MCP
    key of the user in the Authorization header (Bearer)."""

    @route('/mcp', type='http', auth='public', methods=['GET', 'POST', 'DELETE', 'OPTIONS'], csrf=False,
           save_session=False, sitemap=False)
    def mcp(self, **kwargs):
        httprequest = request.httprequest
        origin = httprequest.headers.get('Origin')
        if origin and not self._mcp_origin_allowed(origin):
            return self._mcp_error_response(403, INVALID_REQUEST, 'Origin not allowed')
        cors = self._mcp_cors_headers(origin)
        if httprequest.method == 'OPTIONS':
            return request.make_response('', headers=cors + [
                ('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS'),
                ('Access-Control-Max-Age', '86400'),
            ], status=204)
        if not request.env['ir.config_parameter'].sudo().get_bool('om_ai_mcp.enabled'):
            return self._mcp_error_response(403, INVALID_REQUEST, 'The MCP server is disabled', headers=cors)

        auth = self._mcp_authenticate()
        if isinstance(auth, tuple):
            status, message = auth
            headers = list(cors)
            if status == 401:
                headers.append(('WWW-Authenticate', self._mcp_challenge(
                    bool(request.httprequest.headers.get('Authorization')))))
            return self._mcp_error_response(status, INVALID_REQUEST, message, headers=headers)
        key = auth

        if httprequest.method == 'GET':
            # no stream of server messages: this server only answers requests
            return request.make_response('', headers=cors + [('Allow', 'POST, DELETE')], status=405)
        session = None
        token = httprequest.headers.get(SESSION_HEADER)
        if token:
            session = self._mcp_find_session(key, token)
            if not session:
                return self._mcp_error_response(404, INVALID_REQUEST, 'Session not found', headers=cors)
        if httprequest.method == 'DELETE':
            if not session:
                return self._mcp_error_response(400, INVALID_REQUEST, 'Mcp-Session-Id header required', headers=cors)
            self._mcp_write_session(session, {'active': False})
            return request.make_response('', headers=cors, status=204)
        return self._mcp_post(key, session, cors)

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def _mcp_post(self, key, session, cors):
        httprequest = request.httprequest
        accept = httprequest.headers.get('Accept') or '*/*'
        wants_json = 'application/json' in accept or '*/*' in accept
        wants_sse = 'text/event-stream' in accept
        if not wants_json and not wants_sse:
            return self._mcp_error_response(406, INVALID_REQUEST,
                                            'Accept application/json or text/event-stream', headers=cors)
        header_version = httprequest.headers.get(VERSION_HEADER)
        if header_version and header_version not in PROTOCOL_VERSIONS:
            return self._mcp_error_response(400, INVALID_REQUEST,
                                            'Unsupported MCP-Protocol-Version: %s' % header_version, headers=cors)
        version = header_version or (session and session['protocol_version']) or DEFAULT_VERSION
        try:
            body = json.loads(httprequest.get_data(as_text=True) or 'null')
        except ValueError:
            return self._mcp_error_response(400, PARSE_ERROR, 'Parse error', headers=cors)

        batch = isinstance(body, list)
        if batch and (version != '2025-03-26' or not body):
            # JSON-RPC batches exist only in the 2025-03-26 revision
            return self._mcp_error_response(400, INVALID_REQUEST, 'Batch requests are not supported', headers=cors)
        messages = body if batch else [body]
        responses = []
        extra_headers = []
        for message in messages:
            answer, new_session = self._mcp_handle_message(key, session, version, message, batch)
            if new_session:
                extra_headers.append((SESSION_HEADER, new_session))
            if answer is not None:
                responses.append(answer)
            if isinstance(answer, dict) and answer.get('_http_status'):
                status = answer.pop('_http_status')
                retry = answer.pop('_retry_after', None)
                headers = cors + ([('Retry-After', str(retry))] if retry else [])
                return request.make_json_response(answer, headers=headers, status=status)
        if not responses:
            return request.make_response('', headers=cors + extra_headers, status=202)
        payload = responses if batch else responses[0]
        headers = cors + extra_headers
        if wants_sse and not wants_json:
            data = json.dumps(payload, ensure_ascii=False, default=str)
            return request.make_response('event: message\ndata: %s\n\n' % data, headers=headers + [
                ('Content-Type', 'text/event-stream'), ('Cache-Control', 'no-cache'),
            ])
        return request.make_response(json.dumps(payload, ensure_ascii=False, default=str), headers=headers + [
            ('Content-Type', 'application/json'),
        ])

    def _mcp_handle_message(self, key, session, version, message, batch):
        """Return (response or None, new session id or None)."""
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
            return self._mcp_rpc_error(None, INVALID_REQUEST, 'Invalid Request'), None
        if 'method' not in message:
            # a response to a request of ours: there are none, accept and ignore it
            return None, None
        method = message.get('method')
        is_request = 'id' in message
        if not isinstance(method, str) or (is_request and not isinstance(message['id'], (str, int))):
            return self._mcp_rpc_error(message.get('id'), INVALID_REQUEST, 'Invalid Request'), None
        if not is_request:
            return None, None  # notifications: initialized, cancelled, ...
        request_id = message['id']
        log = {'method': method[:100], 'status': 'success', 'client_name': session and session['client_name'],
               'auth_type': key['auth'], 'grant_id': key['grant_id'] or False}
        params = message.get('params')
        if method == 'tools/call' and isinstance(params, dict) and isinstance(params.get('name'), str):
            log['tool'] = params['name'][:100]
        if method != 'ping':
            limited = self._mcp_rate_limited(key)
            if limited:
                log.update(status='rate_limited', error='Rate limit reached')
                self._mcp_log(key, session, log, 0)
                answer = self._mcp_rpc_error(request_id, INVALID_REQUEST,
                                             'Rate limit reached, retry in %s seconds' % limited)
                answer['_http_status'] = 429
                answer['_retry_after'] = limited
                return answer, None
        if method == 'initialize' and batch:
            return self._mcp_rpc_error(request_id, INVALID_REQUEST, 'initialize cannot be sent in a batch'), None
        env = self._mcp_env(key)
        info = {
            'protocol_version': version,
            'read_only': key['scope'] == 'mcp_read',
            'client_name': session and session['client_name'],
        }
        started = time.monotonic()
        new_session = None
        try:
            with env.cr.savepoint():
                result = env['om.mcp.server']._mcp_dispatch(method, message.get('params'), info)
            answer = {'jsonrpc': '2.0', 'id': request_id, 'result': result}
            if method == 'initialize':
                new_session, session = self._mcp_create_session(key, info)
        except McpError as error:
            log.update(status=error.status, error=error.message)
            answer = self._mcp_rpc_error(request_id, error.code, error.message, error.data)
        except (psycopg2.OperationalError, ConcurrencyError):
            raise  # Odoo retries the request
        except Exception:  # noqa: BLE001 - never send a traceback to the client
            _logger.exception('MCP request %s failed', method)
            log.update(status='error', error='Internal error')
            answer = self._mcp_rpc_error(request_id, INTERNAL_ERROR, 'Internal error')
        for name in ('tool', 'model', 'target', 'status', 'error'):
            if info.get(name):
                log[name] = info[name]
        log['client_name'] = info.get('client_name') or log['client_name']
        self._mcp_log(key, session, log, (time.monotonic() - started) * 1000)
        if session and not new_session:
            self._mcp_touch_session(session)
        return answer, new_session

    # ------------------------------------------------------------------
    # Authentication, environment, limits
    # ------------------------------------------------------------------
    def _mcp_authenticate(self):
        """Return the key dict, or (http status, message). The bearer is an
        MCP key of the user or an OAuth access token of a connected app."""
        header = request.httprequest.headers.get('Authorization') or ''
        match = re.match(r'^bearer\s+(\S+)\s*$', header, re.IGNORECASE)
        if not match:
            return 401, 'Missing Authorization: Bearer <MCP key or access token> header'
        value = match.group(1)
        if value.startswith(ACCESS_PREFIX):
            return self._mcp_authenticate_oauth(value)
        found = request.env['res.users.apikeys'].sudo()._mcp_check_key(value)
        if not found:
            _logger.info('MCP: invalid key from %s', request.httprequest.remote_addr)
            return 401, 'Invalid or expired MCP key'
        key_id, user_id, scope, name = found
        user = request.env['res.users'].sudo().browse(user_id)
        if user.share or not user.has_group('om_ai_mcp.group_mcp_user'):
            return 403, 'The user of this key is not an MCP user'
        return {'id': key_id, 'grant_id': False, 'auth': 'key', 'user_id': user_id, 'scope': scope, 'name': name}

    def _mcp_authenticate_oauth(self, value):
        if not request.env['ir.config_parameter'].sudo().get_bool('om_ai_mcp.oauth_enabled'):
            return 401, 'OAuth sign-in is turned off'
        grant = request.env['om.mcp.oauth.grant'].sudo()._check_access_token(value)
        if not grant:
            _logger.info('MCP: invalid access token from %s', request.httprequest.remote_addr)
            return 401, 'Invalid or expired access token'
        # the token must have been issued for this server (audience)
        if canonical_uri(grant.resource) not in self._mcp_resource_uris():
            return 401, 'The access token was issued for another resource'
        user = grant.user_id
        if user.share or not user.has_group('om_ai_mcp.group_mcp_user'):
            return 403, 'The user of this app connection is not an MCP user'
        self._mcp_touch_grant(grant)
        return {'id': False, 'grant_id': grant.id, 'auth': 'oauth', 'user_id': user.id,
                'scope': KEY_SCOPES[grant.scope], 'name': grant.client_name}

    def _mcp_resource_uris(self):
        uris = {canonical_uri(mcp_resource_url())}
        base = self._mcp_param('web.base.url')
        if base:
            uris.add(canonical_uri('%s/mcp' % base.rstrip('/')))
        return uris

    def _mcp_challenge(self, token_sent):
        params = ['realm="odoo"']
        if request.env['ir.config_parameter'].sudo().get_bool('om_ai_mcp.oauth_enabled'):
            params += ['resource_metadata="%s"' % resource_metadata_url(), 'scope="%s"' % SCOPE_WRITE]
        if token_sent:
            params.append('error="invalid_token"')
        return 'Bearer %s' % ', '.join(params)

    def _mcp_touch_grant(self, grant):
        last = grant.last_used
        if not last or (fields.Datetime.now() - last).total_seconds() > SESSION_TOUCH_SECONDS:
            with request.env.registry.cursor() as cr:
                self._mcp_sudo_env(cr)['om.mcp.oauth.grant'].browse(grant.id).write(
                    {'last_used': fields.Datetime.now()})

    def _mcp_env(self, key):
        request.update_env(user=key['user_id'])
        user = request.env.user
        context = dict(request.env.context, lang=user.lang or request.env.context.get('lang'), tz=user.tz,
                       om_mcp_key_id=key['id'], om_mcp_grant_id=key['grant_id'],
                       om_mcp_read_only=key['scope'] == 'mcp_read')
        context.pop('allowed_company_ids', None)
        request.update_context(**context)
        return request.env

    def _mcp_param(self, name, default=''):
        return request.env['ir.config_parameter'].sudo().get_str(name, default)

    def _mcp_rate_limited(self, key):
        """Seconds to wait when the key made too many requests in the window, else 0."""
        params = request.env['ir.config_parameter'].sudo()
        limit = params.get_int('om_ai_mcp.rate_limit', 120)
        window = max(1, params.get_int('om_ai_mcp.rate_window', 60))
        if limit <= 0:
            return 0
        if request.env['om.mcp.log'].sudo()._count_recent(key['id'], window, key['grant_id']) >= limit:
            return window
        return 0

    def _mcp_origin_allowed(self, origin):
        own = urlsplit(request.httprequest.host_url)
        base = urlsplit(self._mcp_param('web.base.url') or '')
        parsed = urlsplit(origin)
        if (parsed.scheme, parsed.netloc) in ((own.scheme, own.netloc), (base.scheme, base.netloc)):
            return True
        allowed = [item.strip().rstrip('/') for item in (self._mcp_param('om_ai_mcp.allowed_origins') or '').split(',')]
        return origin.rstrip('/') in [item for item in allowed if item]

    def _mcp_cors_headers(self, origin):
        if not origin:
            return []
        return [
            ('Access-Control-Allow-Origin', origin),
            ('Access-Control-Allow-Headers', CORS_HEADERS),
            ('Access-Control-Expose-Headers', '%s, WWW-Authenticate' % SESSION_HEADER),
            ('Vary', 'Origin'),
        ]

    # ------------------------------------------------------------------
    # Sessions and log (own transactions: kept when the request fails)
    # ------------------------------------------------------------------
    def _mcp_sudo_env(self, cr):
        return api.Environment(cr, SUPERUSER_ID, {})

    def _mcp_find_session(self, key, token):
        owner = ('grant_id', '=', key['grant_id']) if key['grant_id'] else ('key_id', '=', key['id'])
        session = request.env['om.mcp.session'].sudo().search([
            ('token_hash', '=', request.env['om.mcp.session']._hash(token)), owner,
        ], limit=1)
        if not session:
            return None
        return {'id': session.id, 'protocol_version': session.protocol_version, 'client_name': session.client_name,
                'last_activity': session.last_activity}

    def _mcp_create_session(self, key, info):
        token = secrets.token_urlsafe(32)
        with request.env.registry.cursor() as cr:
            session = self._mcp_sudo_env(cr)['om.mcp.session'].create({
                'token_hash': self._mcp_sudo_env(cr)['om.mcp.session']._hash(token),
                'user_id': key['user_id'],
                'key_id': key['id'],
                'key_name': key['name'],
                'grant_id': key['grant_id'],
                'protocol_version': info.get('protocol_version'),
                'client_name': info.get('client_name'),
                'client_version': info.get('client_version'),
            })
            values = {'id': session.id, 'protocol_version': session.protocol_version,
                      'client_name': session.client_name, 'last_activity': session.last_activity}
        return token, values

    def _mcp_write_session(self, session, values):
        with request.env.registry.cursor() as cr:
            self._mcp_sudo_env(cr)['om.mcp.session'].browse(session['id']).write(values)

    def _mcp_touch_session(self, session):
        last = session.get('last_activity')
        if not last or (fields.Datetime.now() - last).total_seconds() > SESSION_TOUCH_SECONDS:
            self._mcp_write_session(session, {'last_activity': fields.Datetime.now()})
            session['last_activity'] = fields.Datetime.now()

    def _mcp_log(self, key, session, values, duration):
        user = request.env['res.users'].sudo().browse(key['user_id'])
        values = dict(values, user_id=user.id, company_id=user.company_id.id, key_id=key['id'],
                      key_name=key['name'], key_scope=key['scope'], session_id=session and session['id'],
                      duration=duration, ip=request.httprequest.remote_addr)
        if values.get('error'):
            values['error'] = str(values['error'])[:2000]
        try:
            with request.env.registry.cursor() as cr:
                self._mcp_sudo_env(cr)['om.mcp.log'].create(values)
        except Exception:  # noqa: BLE001 - the answer must not fail because of the log
            _logger.exception('Could not write the MCP log')

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------
    @staticmethod
    def _mcp_rpc_error(request_id, code, message, data=None):
        error = {'code': code, 'message': message}
        if data is not None:
            error['data'] = data
        return {'jsonrpc': '2.0', 'id': request_id, 'error': error}

    def _mcp_error_response(self, status, code, message, headers=None):
        return request.make_json_response(self._mcp_rpc_error(None, code, message), headers=headers or [],
                                          status=status)
