import base64
import binascii
import hmac
import json
import logging
from datetime import timedelta
from urllib.parse import parse_qsl, quote, unquote_plus, urlencode, urlsplit, urlunsplit

from odoo import fields
from odoo.http import Controller, request, route
from odoo.tools import SQL

from odoo.addons.om_ai_mcp.models.om_mcp_oauth import (
    AUTH_METHODS,
    CHALLENGE,
    SCOPE_READ,
    SCOPE_WRITE,
    SCOPES,
    VERIFIER,
    check_redirect_uri,
    is_loopback_host,
    pkce_s256,
    token_hash,
)

_logger = logging.getLogger(__name__)

METADATA_PATH = '/.well-known/oauth-protected-resource'
AS_METADATA_PATH = '/.well-known/oauth-authorization-server'
AUTHORIZE_PATH = '/mcp/oauth/authorize'
TOKEN_PATH = '/mcp/oauth/token'
REGISTER_PATH = '/mcp/oauth/register'
REVOKE_PATH = '/mcp/oauth/revoke'
REGISTRATIONS_PER_HOUR = 30
NO_STORE = [('Cache-Control', 'no-store'), ('Pragma', 'no-cache')]
OPEN_CORS = [
    ('Access-Control-Allow-Origin', '*'),
    ('Access-Control-Allow-Headers', 'Authorization, Content-Type, MCP-Protocol-Version'),
    ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
    ('Access-Control-Max-Age', '86400'),
]
FRAME_HEADERS = [('X-Frame-Options', 'DENY'), ('Content-Security-Policy', "frame-ancestors 'none'")]


def base_url():
    return request.httprequest.url_root.rstrip('/')


def mcp_resource_url():
    return '%s/mcp' % base_url()


def resource_metadata_url():
    return '%s%s/mcp' % (base_url(), METADATA_PATH)


def canonical_uri(uri):
    """Lower case scheme and host, no fragment, no trailing slash."""
    parts = urlsplit((uri or '').strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query, ''))


class OAuthError(Exception):
    def __init__(self, error, description, status=400):
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status


class OmMcpOauthController(Controller):
    """OAuth 2.1 authorization server of the MCP endpoint: metadata (RFC 8414,
    RFC 9728), dynamic client registration (RFC 7591), the authorization code
    flow with PKCE S256 (RFC 7636), resource indicators (RFC 8707), refresh
    token rotation and revocation (RFC 7009)."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _oauth_param(self, name):
        return request.env['ir.config_parameter'].sudo().get_str(name)

    def _oauth_enabled(self):
        params = request.env['ir.config_parameter'].sudo()
        return params.get_bool('om_ai_mcp.enabled') and params.get_bool('om_ai_mcp.oauth_enabled')

    def _json(self, data, status=200, headers=None):
        return request.make_json_response(data, status=status, headers=(headers or []) + OPEN_CORS)

    def _oauth_error(self, error, description, status=400, headers=None):
        return self._json({'error': error, 'error_description': description}, status=status,
                          headers=(headers or []) + NO_STORE)

    def _preflight(self):
        return request.make_response('', headers=OPEN_CORS, status=204)

    def _not_found(self):
        return request.make_json_response({'error': 'not_found'}, status=404, headers=OPEN_CORS)

    def _resource_uris(self):
        uris = {canonical_uri(mcp_resource_url())}
        configured = self._oauth_param('web.base.url')
        if configured:
            uris.add(canonical_uri('%s/mcp' % configured.rstrip('/')))
        return uris

    def _check_resource(self, resource):
        """The canonical resource the token is for: this MCP endpoint."""
        if not resource:
            return mcp_resource_url()
        if canonical_uri(resource) in self._resource_uris() or canonical_uri(resource) in {
                canonical_uri(base_url()), canonical_uri(self._oauth_param('web.base.url') or '')}:
            return mcp_resource_url()
        raise OAuthError('invalid_target', 'The resource must be this MCP server: %s' % mcp_resource_url())

    @staticmethod
    def _scopes(scope):
        """Requested scopes; no scope means the full access the user may grant."""
        values = [item for item in (scope or '').split() if item]
        unknown = [item for item in values if item not in SCOPES]
        if unknown:
            raise OAuthError('invalid_scope', 'Unknown scope: %s' % ' '.join(unknown))
        return values or [SCOPE_WRITE]

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    @route([METADATA_PATH, '%s/mcp' % METADATA_PATH], type='http', auth='public', methods=['GET', 'OPTIONS'],
           csrf=False, save_session=False, sitemap=False, readonly=True)
    def oauth_protected_resource(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._preflight()
        if not self._oauth_enabled():
            return self._not_found()
        return self._json({
            'resource': mcp_resource_url(),
            'authorization_servers': [base_url()],
            'scopes_supported': list(SCOPES),
            'bearer_methods_supported': ['header'],
            'resource_name': request.env.company.sudo().name or 'Odoo',
        })

    @route(AS_METADATA_PATH, type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False,
           save_session=False, sitemap=False, readonly=True)
    def oauth_authorization_server(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._preflight()
        if not self._oauth_enabled():
            return self._not_found()
        base = base_url()
        metadata = {
            'issuer': base,
            'authorization_endpoint': base + AUTHORIZE_PATH,
            'token_endpoint': base + TOKEN_PATH,
            'revocation_endpoint': base + REVOKE_PATH,
            'response_types_supported': ['code'],
            'response_modes_supported': ['query'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'code_challenge_methods_supported': ['S256'],
            'token_endpoint_auth_methods_supported': list(AUTH_METHODS),
            'revocation_endpoint_auth_methods_supported': list(AUTH_METHODS),
            'scopes_supported': list(SCOPES),
            'authorization_response_iss_parameter_supported': True,
        }
        if request.env['ir.config_parameter'].sudo().get_bool('om_ai_mcp.oauth_registration'):
            metadata['registration_endpoint'] = base + REGISTER_PATH
        return self._json(metadata)

    # ------------------------------------------------------------------
    # Dynamic client registration
    # ------------------------------------------------------------------
    @route(REGISTER_PATH, type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False,
           save_session=False, sitemap=False)
    def oauth_register(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._preflight()
        params = request.env['ir.config_parameter'].sudo()
        if not self._oauth_enabled() or not params.get_bool('om_ai_mcp.oauth_registration'):
            return self._oauth_error('access_denied', 'Apps cannot register themselves on this server', status=403)
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or 'null')
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self._oauth_error('invalid_client_metadata', 'The body must be a JSON object')
        ip = request.httprequest.remote_addr
        Client = request.env['om.mcp.oauth.client'].sudo()
        recent = Client.search_count([('ip', '=', ip), ('registration', '=', 'dynamic'),
                                      ('create_date', '>', fields.Datetime.now() - timedelta(hours=1))])
        if recent >= REGISTRATIONS_PER_HOUR:
            return self._oauth_error('invalid_client_metadata', 'Too many registrations, try again later',
                                     status=429)
        try:
            values = self._registration_values(body)
        except OAuthError as error:
            return self._oauth_error(error.error, error.description, status=error.status)
        values.update(registration='dynamic', ip=ip,
                      state='pending' if params.get_bool('om_ai_mcp.oauth_registration_approval') else 'approved')
        secret = None
        if values['auth_method'] != 'none':
            secret = Client._new_secret()
            values['secret_hash'] = token_hash(secret)
        client = Client.create(values)
        _logger.info('MCP OAuth: app "%s" registered from %s (%s)', client.name, ip, client.state)
        answer = {
            'client_id': client.client_id,
            'client_id_issued_at': int(client.create_date.timestamp()),
            'client_name': client.name,
            'redirect_uris': client._get_redirect_uris(),
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'],
            'token_endpoint_auth_method': client.auth_method,
            'scope': ' '.join(SCOPES),
        }
        for key, field in (('client_uri', 'client_uri'), ('logo_uri', 'logo_uri'), ('software_id', 'software_id'),
                           ('software_version', 'software_version')):
            if client[field]:
                answer[key] = client[field]
        if secret:
            answer.update(client_secret=secret, client_secret_expires_at=0)
        return self._json(answer, status=201, headers=NO_STORE)

    def _registration_values(self, body):
        uris = body.get('redirect_uris')
        if not isinstance(uris, list) or not uris or not all(isinstance(uri, str) for uri in uris) or len(uris) > 10:
            raise OAuthError('invalid_redirect_uri', 'redirect_uris must be a list of 1 to 10 URIs')
        for uri in uris:
            error = check_redirect_uri(uri)
            if error:
                raise OAuthError('invalid_redirect_uri', '%s: %s' % (uri, error))
        # RFC 7591: the default is client_secret_basic
        method = body.get('token_endpoint_auth_method') or 'client_secret_basic'
        if method not in AUTH_METHODS:
            raise OAuthError('invalid_client_metadata', 'token_endpoint_auth_method must be one of %s' % (
                ', '.join(AUTH_METHODS)))
        grant_types = body.get('grant_types') or ['authorization_code']
        if not isinstance(grant_types, list) or set(grant_types) - {'authorization_code', 'refresh_token'}:
            raise OAuthError('invalid_client_metadata', 'Only the authorization_code and refresh_token grants '
                                                        'are supported')
        response_types = body.get('response_types') or ['code']
        if not isinstance(response_types, list) or set(response_types) - {'code'}:
            raise OAuthError('invalid_client_metadata', 'Only the code response type is supported')
        if body.get('scope'):
            self._scopes(str(body['scope']))
        values = {
            'name': str(body.get('client_name') or 'MCP app').strip()[:100] or 'MCP app',
            'redirect_uris': '\n'.join(uris),
            'auth_method': method,
        }
        for key in ('client_uri', 'logo_uri'):
            value = body.get(key)
            if value:
                if not isinstance(value, str) or urlsplit(value).scheme != 'https' or len(value) > 500:
                    raise OAuthError('invalid_client_metadata', '%s must be an https URL' % key)
                values[key] = value
        for key in ('software_id', 'software_version'):
            if body.get(key):
                values[key] = str(body[key])[:100]
        return values

    # ------------------------------------------------------------------
    # Authorization endpoint
    # ------------------------------------------------------------------
    def _render_error(self, title, message, status=400):
        response = request.render('om_ai_mcp.oauth_error', {'title': title, 'message': message})
        response.status_code = status
        response.headers.extend(FRAME_HEADERS + NO_STORE)
        return response

    def _redirect(self, redirect_uri, values):
        parts = urlsplit(redirect_uri)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query += [(key, value) for key, value in values.items() if value is not None]
        location = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ''))
        response = request.redirect(location, code=303, local=False)
        response.headers.extend(NO_STORE)
        return response

    def _check_authorize_request(self, params):
        """Validate the request. Return (client, redirect_uri, values) or raise:
        a tuple (title, message) for errors shown on the page (bad app or
        redirect URI), an OAuthError for errors sent to the app."""
        _ = request.env._
        client = request.env['om.mcp.oauth.client']._find(params.get('client_id'))
        if not client or not client.active or client.state == 'blocked':
            raise ValueError(_('Unknown app'), _('This app is not known to Odoo or was blocked by an administrator.'))
        redirect_uri = params.get('redirect_uri')
        if not redirect_uri:
            registered = client._get_redirect_uris()
            if len(registered) != 1:
                raise ValueError(_('Invalid request'), _('The app did not say where to send the answer.'))
            redirect_uri = registered[0]
        if not client._redirect_allowed(redirect_uri):
            raise ValueError(_('Invalid request'), _('The app asked to send the answer to an address it did not '
                                                     'register: %s', redirect_uri))
        if client.state == 'pending':
            raise ValueError(_('Waiting for approval'), _('The app "%s" registered on this database and waits for '
                                                          'an administrator to approve it. Try again later.',
                                                          client.name))
        try:
            if params.get('response_type') != 'code':
                raise OAuthError('unsupported_response_type', 'response_type must be code')
            challenge = params.get('code_challenge') or ''
            if params.get('code_challenge_method') != 'S256' or not CHALLENGE.match(challenge):
                raise OAuthError('invalid_request', 'PKCE with code_challenge_method S256 is required')
            scopes = self._scopes(params.get('scope'))
            resource = self._check_resource(params.get('resource'))
        except OAuthError as error:
            error.redirect_uri = redirect_uri
            raise
        return client, redirect_uri, {
            'client_id': client.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'state': params.get('state') or '',
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'scope': ' '.join(scopes),
            'resource': resource,
        }

    @route(AUTHORIZE_PATH, type='http', auth='public', methods=['GET'], sitemap=False)
    def oauth_authorize(self, **params):
        _ = request.env._
        if not self._oauth_enabled():
            return self._render_error(_('Not available'), _('Signing in AI apps with OAuth is turned off.'), 404)
        try:
            client, redirect_uri, values = self._check_authorize_request(params)
        except ValueError as error:
            return self._render_error(*error.args)
        except OAuthError as error:
            return self._redirect(error.redirect_uri, {
                'error': error.error, 'error_description': error.description,
                'state': params.get('state') or None, 'iss': base_url()})
        user = request.env.user
        if user._is_public():
            target = '%s?%s' % (AUTHORIZE_PATH, urlencode(values))
            return request.redirect('/web/login?redirect=%s' % quote(target, safe=''))
        if user.share or not user.has_group('om_ai_mcp.group_mcp_user'):
            return self._render_error(_('Access refused'), _('Your user may not connect AI apps. Ask your '
                                                              'administrator for the MCP Server / MCP User access.'),
                                      403)
        redirect_host = urlsplit(redirect_uri).hostname or urlsplit(redirect_uri).scheme
        response = request.render('om_ai_mcp.oauth_consent', {
            'client': client,
            'values': values,
            'user': user,
            'database': request.db,
            'redirect_host': redirect_host,
            'client_host': urlsplit(client.client_uri).hostname if client.client_uri else False,
            'loopback': is_loopback_host(urlsplit(redirect_uri).hostname),
            'can_write': SCOPE_WRITE in values['scope'].split(),
        })
        response.headers.extend(FRAME_HEADERS + NO_STORE)
        return response

    @route(AUTHORIZE_PATH, type='http', auth='user', methods=['POST'], sitemap=False)
    def oauth_authorize_post(self, decision=None, allow_write=None, **params):
        _ = request.env._
        if not self._oauth_enabled():
            return self._render_error(_('Not available'), _('Signing in AI apps with OAuth is turned off.'), 404)
        try:
            client, redirect_uri, values = self._check_authorize_request(params)
        except ValueError as error:
            return self._render_error(*error.args)
        except OAuthError as error:
            return self._render_error(_('Invalid request'), error.description)
        user = request.env.user
        if user.share or not user.has_group('om_ai_mcp.group_mcp_user'):
            return self._render_error(_('Access refused'), _('Your user may not connect AI apps.'), 403)
        state = values['state'] or None
        if decision != 'allow':
            return self._redirect(redirect_uri, {'error': 'access_denied', 'error_description': 'The user refused '
                                                 'the access', 'state': state, 'iss': base_url()})
        scope = SCOPE_WRITE if allow_write and SCOPE_WRITE in values['scope'].split() else SCOPE_READ
        code = request.env['om.mcp.oauth.code'].sudo()._new(client, user, redirect_uri, values['code_challenge'],
                                                             scope, values['resource'])
        _logger.info('MCP OAuth: %s allowed app "%s" (%s)', user.login, client.name, scope)
        return self._redirect(redirect_uri, {'code': code, 'state': state, 'iss': base_url()})

    # ------------------------------------------------------------------
    # Token endpoint
    # ------------------------------------------------------------------
    def _authenticate_client(self, params):
        """Return the app of the request (client_secret_basic, _post or a public
        app with its client_id), or raise an OAuthError."""
        header = request.httprequest.headers.get('Authorization') or ''
        client_id, secret, method = params.get('client_id'), params.get('client_secret'), 'none'
        if header.lower().startswith('basic '):
            try:
                decoded = base64.b64decode(header[6:].strip(), validate=True).decode()
                basic_id, _sep, basic_secret = decoded.partition(':')
            except (binascii.Error, UnicodeDecodeError, ValueError):
                raise OAuthError('invalid_client', 'Malformed Basic authorization', 401) from None
            basic_id, basic_secret = unquote_plus(basic_id), unquote_plus(basic_secret)
            if client_id and client_id != basic_id:
                raise OAuthError('invalid_client', 'Two different client ids', 401)
            client_id, secret, method = basic_id, basic_secret, 'client_secret_basic'
        elif secret:
            method = 'client_secret_post'
        client = request.env['om.mcp.oauth.client']._find(client_id)
        if not client or not client._usable():
            raise OAuthError('invalid_client', 'Unknown or blocked app', 401)
        if client.auth_method == 'none':
            if secret:
                raise OAuthError('invalid_client', 'This app has no secret', 401)
        elif method == 'none' or not client._check_secret(secret):
            raise OAuthError('invalid_client', 'Client authentication failed', 401)
        return client

    def _lock(self, record):
        request.env.cr.execute(SQL('SELECT id FROM %s WHERE id = %s FOR UPDATE', SQL.identifier(record._table),
                                   record.id))
        record.invalidate_recordset()

    @route(TOKEN_PATH, type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, save_session=False,
           sitemap=False)
    def oauth_token(self, **params):
        if request.httprequest.method == 'OPTIONS':
            return self._preflight()
        if not self._oauth_enabled():
            return self._oauth_error('invalid_request', 'OAuth is turned off', status=404)
        try:
            client = self._authenticate_client(params)
            grant_type = params.get('grant_type')
            if grant_type == 'authorization_code':
                answer = self._token_from_code(client, params)
            elif grant_type == 'refresh_token':
                answer = self._token_from_refresh(client, params)
            else:
                raise OAuthError('unsupported_grant_type', 'grant_type must be authorization_code or refresh_token')
        except OAuthError as error:
            headers = [('WWW-Authenticate', 'Basic realm="odoo"')] if error.status == 401 and \
                (request.httprequest.headers.get('Authorization') or '').lower().startswith('basic ') else []
            return self._oauth_error(error.error, error.description, status=error.status, headers=headers)
        return self._json(answer, headers=NO_STORE)

    def _token_from_code(self, client, params):
        Code = request.env['om.mcp.oauth.code'].sudo()
        code = Code._find(params.get('code'))
        if not code:
            raise OAuthError('invalid_grant', 'Invalid authorization code')
        self._lock(code)
        if code.used:
            # a code used twice: it may have been stolen, end what it gave
            _logger.warning('MCP OAuth: authorization code of app "%s" used twice', code.client_id.name)
            code.grant_id._revoke()
            raise OAuthError('invalid_grant', 'The authorization code was already used')
        if code.client_id != client:
            raise OAuthError('invalid_grant', 'The authorization code was issued to another app')
        if code.expires < fields.Datetime.now():
            raise OAuthError('invalid_grant', 'The authorization code expired')
        redirect_uri = params.get('redirect_uri')
        if redirect_uri is not None and not hmac.compare_digest(redirect_uri.encode(), code.redirect_uri.encode()):
            raise OAuthError('invalid_grant', 'redirect_uri does not match the authorization request')
        verifier = params.get('code_verifier') or ''
        if not VERIFIER.match(verifier) or not hmac.compare_digest(pkce_s256(verifier).encode(),
                                                                   code.code_challenge.encode()):
            raise OAuthError('invalid_grant', 'PKCE verification failed')
        if params.get('resource') and canonical_uri(self._check_resource(params['resource'])) != \
                canonical_uri(code.resource):
            raise OAuthError('invalid_target', 'The resource does not match the authorization request')
        user = code.user_id
        if not user.active or user.share or not user.has_group('om_ai_mcp.group_mcp_user'):
            raise OAuthError('invalid_grant', 'The user may not use the MCP server')
        grant = request.env['om.mcp.oauth.grant'].sudo().create({
            'client_id': client.id,
            'user_id': user.id,
            'scope': code.scope,
            'resource': code.resource,
            'redirect_uri': code.redirect_uri,
        })
        code.write({'used': True, 'grant_id': grant.id})
        return grant._issue_tokens()

    def _token_from_refresh(self, client, params):
        Token = request.env['om.mcp.oauth.token'].sudo()
        value = params.get('refresh_token') or ''
        token = Token.search([('token_hash', '=', token_hash(value)), ('kind', '=', 'refresh')], limit=1) \
            if value else Token
        if not token:
            raise OAuthError('invalid_grant', 'Invalid refresh token')
        self._lock(token)
        grant = token.grant_id
        if grant.client_id != client:
            raise OAuthError('invalid_grant', 'The refresh token was issued to another app')
        if token.used:
            # rotation: an old refresh token came back, someone else may hold it
            grant._revoke()
            _logger.warning('MCP OAuth: refresh token of app "%s" used twice, connection ended', client.name)
            raise OAuthError('invalid_grant', 'The refresh token was already used')
        if token.expires < fields.Datetime.now() or not grant.active:
            raise OAuthError('invalid_grant', 'The refresh token expired or was revoked')
        if params.get('scope'):
            scopes = self._scopes(params['scope'])
            if grant.scope == SCOPE_READ and SCOPE_WRITE in scopes:
                raise OAuthError('invalid_scope', 'The app was allowed to read only')
        if params.get('resource') and canonical_uri(self._check_resource(params['resource'])) != \
                canonical_uri(grant.resource):
            raise OAuthError('invalid_target', 'The resource does not match the connection')
        user = grant.user_id
        if not user.active or user.share or not user.has_group('om_ai_mcp.group_mcp_user'):
            grant._revoke()
            raise OAuthError('invalid_grant', 'The user may not use the MCP server')
        token.used = True
        return grant._issue_tokens(parent=token)

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------
    @route(REVOKE_PATH, type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, save_session=False,
           sitemap=False)
    def oauth_revoke(self, **params):
        if request.httprequest.method == 'OPTIONS':
            return self._preflight()
        if not self._oauth_enabled():
            return self._oauth_error('invalid_request', 'OAuth is turned off', status=404)
        try:
            client = self._authenticate_client(params)
        except OAuthError as error:
            return self._oauth_error(error.error, error.description, status=error.status)
        Token = request.env['om.mcp.oauth.token'].sudo()
        value = params.get('token') or ''
        token = Token.search([('token_hash', '=', token_hash(value))], limit=1) if value else Token
        # unknown tokens are not an error (RFC 7009)
        if token and token.grant_id.client_id == client:
            if token.kind == 'refresh':
                token.grant_id._revoke()
            else:
                token.unlink()
        return self._json({}, headers=NO_STORE)
