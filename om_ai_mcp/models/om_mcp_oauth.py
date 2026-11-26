import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain

# OAuth scopes and the access they give
SCOPE_WRITE = 'mcp'
SCOPE_READ = 'mcp:read'
SCOPES = (SCOPE_WRITE, SCOPE_READ)
KEY_SCOPES = {SCOPE_WRITE: 'mcp', SCOPE_READ: 'mcp_read'}

ACCESS_PREFIX = 'mcpat_'
REFRESH_PREFIX = 'mcprt_'
CODE_PREFIX = 'mcpac_'
SECRET_PREFIX = 'mcpcs_'

CODE_SECONDS = 120
VERIFIER = re.compile(r'^[A-Za-z0-9\-._~]{43,128}$')
CHALLENGE = re.compile(r'^[A-Za-z0-9\-_]{43}$')
BLOCKED_SCHEMES = ('javascript', 'data', 'file', 'vbscript', 'about', 'blob')
AUTH_METHODS = ('none', 'client_secret_post', 'client_secret_basic')


def token_hash(value):
    return hashlib.sha256((value or '').encode()).hexdigest()


def pkce_s256(verifier):
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')


def is_loopback_host(host):
    host = (host or '').strip('[]').lower()
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_redirect_uri(uri):
    """Return an error text when the redirect URI may not be registered."""
    if not uri or len(uri) > 2000 or any(char.isspace() for char in uri):
        return 'redirect URIs must be absolute URIs without spaces'
    parts = urlsplit(uri)
    scheme = parts.scheme.lower()
    if not scheme or parts.fragment or '#' in uri:
        return 'redirect URIs must be absolute and have no fragment'
    if scheme in BLOCKED_SCHEMES:
        return 'redirect URI scheme %s is not allowed' % scheme
    if scheme == 'http' and not is_loopback_host(parts.hostname):
        return 'http redirect URIs are only allowed for localhost; use https'
    if scheme in ('http', 'https') and not parts.hostname:
        return 'redirect URIs need a host'
    return None


def redirect_matches(registered, given):
    """Exact match, except the port of loopback IP addresses (native apps pick a
    free port when they start)."""
    if hmac.compare_digest(registered.encode(), given.encode()):
        return True
    reg, req = urlsplit(registered), urlsplit(given)
    if reg.scheme == req.scheme == 'http' and reg.hostname and reg.hostname == req.hostname:
        try:
            literal = ipaddress.ip_address(reg.hostname.strip('[]'))
        except ValueError:
            return False
        return literal.is_loopback and reg.path == req.path and reg.query == req.query and not req.fragment
    return False


class OmMcpOauthClient(models.Model):
    """An app allowed to ask users for access to the MCP server with OAuth.
    Apps register themselves (dynamic client registration) or an administrator
    adds them."""
    _name = 'om.mcp.oauth.client'
    _description = 'MCP OAuth App'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='App Name', required=True)
    client_id = fields.Char(string='Client ID', required=True, readonly=True, copy=False, index=True,
                            default=lambda self: 'mcp-%s' % secrets.token_urlsafe(18))
    secret_hash = fields.Char(copy=False, groups='base.group_system')
    auth_method = fields.Selection([
        ('none', 'Public app (PKCE only)'),
        ('client_secret_post', 'Client secret in the body'),
        ('client_secret_basic', 'Client secret in the header'),
    ], string='Client Authentication', default='none', required=True)
    redirect_uris = fields.Text(string='Redirect URIs', required=True, help='One URI per line, matched exactly.')
    client_uri = fields.Char(string='Website')
    logo_uri = fields.Char(string='Logo URL')
    software_id = fields.Char(string='Software')
    software_version = fields.Char()
    registration = fields.Selection([('dynamic', 'Registered by the app'), ('manual', 'Added by an administrator')],
                                    default='manual', required=True, readonly=True)
    state = fields.Selection([
        ('approved', 'Approved'),
        ('pending', 'Waiting for Approval'),
        ('blocked', 'Blocked'),
    ], default='approved', required=True, index=True)
    active = fields.Boolean(default=True)
    ip = fields.Char(string='Registered from', readonly=True)
    grant_ids = fields.One2many('om.mcp.oauth.grant', 'client_id', string='Connections')
    grant_count = fields.Integer(compute='_compute_grant_count', string='Connections Count')
    secret_shown = fields.Char(string='Client Secret', compute='_compute_secret_shown')

    _client_id_unique = models.Constraint('UNIQUE(client_id)', 'The client ID must be unique.')

    def _compute_grant_count(self):
        counts = dict(self.env['om.mcp.oauth.grant']._read_group(
            [('client_id', 'in', self.ids), ('active', '=', True)], ['client_id'], ['__count']))
        for client in self:
            client.grant_count = counts.get(client, 0)

    def _compute_secret_shown(self):
        secret = self.env.context.get('om_mcp_new_secret')
        for client in self:
            client.secret_shown = secret if secret and len(self) == 1 else False

    @api.constrains('redirect_uris')
    def _check_redirect_uris(self):
        for client in self:
            uris = client._get_redirect_uris()
            if not uris:
                raise ValidationError(self.env._('Add at least one redirect URI.'))
            for uri in uris:
                error = check_redirect_uri(uri)
                if error:
                    raise ValidationError(self.env._('Redirect URI %(uri)s: %(error)s', uri=uri, error=error))

    def _get_redirect_uris(self):
        self.ensure_one()
        return [line.strip() for line in (self.redirect_uris or '').splitlines() if line.strip()]

    def _redirect_allowed(self, uri):
        self.ensure_one()
        return bool(uri) and any(redirect_matches(registered, uri) for registered in self._get_redirect_uris())

    @staticmethod
    def _new_secret():
        return SECRET_PREFIX + secrets.token_urlsafe(32)

    def _check_secret(self, secret):
        self.ensure_one()
        stored = self.sudo().secret_hash or ''
        return bool(secret and stored) and hmac.compare_digest(token_hash(secret), stored)

    @api.model
    def _find(self, client_id):
        if not client_id or not isinstance(client_id, str) or len(client_id) > 200:
            return self.browse()
        return self.sudo().search([('client_id', '=', client_id)], limit=1)

    def _usable(self):
        self.ensure_one()
        return self.active and self.state == 'approved'

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_block(self):
        self.write({'state': 'blocked'})
        self.grant_ids.sudo()._revoke()

    def action_new_secret(self):
        self.ensure_one()
        if self.auth_method == 'none':
            raise ValidationError(self.env._('Public apps have no secret: choose a client authentication with a '
                                             'secret first.'))
        secret = self._new_secret()
        self.sudo().secret_hash = token_hash(secret)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(self.env.ref('om_ai_mcp.om_mcp_oauth_client_view_secret').id, 'form')],
            'target': 'new',
            'name': self.env._('Client Secret'),
            'context': {'om_mcp_new_secret': secret},
        }

    def action_view_grants(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_ai_mcp.om_mcp_oauth_grant_action')
        action['domain'] = [('client_id', '=', self.id)]
        action['context'] = {}
        return action

    @api.ondelete(at_uninstall=False)
    def _unlink_revoke(self):
        self.grant_ids.sudo()._revoke()


class OmMcpOauthGrant(models.Model):
    """A connected app: what a user allowed an OAuth app to do. Its tokens are
    kept as hashes only."""
    _name = 'om.mcp.oauth.grant'
    _description = 'MCP Connected App'
    _order = 'create_date desc, id desc'
    _rec_name = 'client_name'

    client_id = fields.Many2one('om.mcp.oauth.client', string='App', required=True, ondelete='cascade', index=True)
    client_name = fields.Char(string='App Name', related='client_id.name', store=True)
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade', index=True)
    scope = fields.Selection([(SCOPE_WRITE, 'Read and write'), (SCOPE_READ, 'Read only')], string='Access',
                             required=True, default=SCOPE_READ)
    resource = fields.Char(string='Resource', required=True)
    redirect_uri = fields.Char(string='Redirect URI')
    last_used = fields.Datetime(string='Last Used')
    expires = fields.Datetime(string='Expires', help='When the app must ask the user again.')
    active = fields.Boolean(default=True)
    revoked = fields.Datetime(string='Revoked On', readonly=True)
    token_ids = fields.One2many('om.mcp.oauth.token', 'grant_id', string='Tokens')
    log_ids = fields.One2many('om.mcp.log', 'grant_id', string='Calls')
    log_count = fields.Integer(compute='_compute_log_count', string='Calls Count')

    _client_index = models.Index('(user_id, client_id)')

    def _compute_log_count(self):
        counts = dict(self.env['om.mcp.log']._read_group([('grant_id', 'in', self.ids)], ['grant_id'], ['__count']))
        for grant in self:
            grant.log_count = counts.get(grant, 0)

    def _revoke(self):
        """End the connection: every token stops working at once."""
        self = self.sudo()
        self.token_ids.unlink()
        self.env['om.mcp.oauth.code'].search([('grant_id', 'in', self.ids)]).unlink()
        self.env['om.mcp.session'].search([('grant_id', 'in', self.ids)]).write({'active': False})
        self.filtered('active').write({'active': False, 'revoked': fields.Datetime.now()})

    def action_revoke(self):
        """Users revoke their own connections, administrators any of them."""
        self.check_access('read')
        if not self.env.user.has_group('om_ai.group_ai_manager') and any(
                grant.user_id != self.env.user for grant in self):
            raise AccessError(self.env._('You may only disconnect your own apps.'))
        self._revoke()
        return True

    def action_view_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_ai_mcp.om_mcp_log_action')
        action['domain'] = [('grant_id', '=', self.id)]
        action['context'] = {}
        return action

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------
    @api.model
    def _lifetimes(self):
        params = self.env['ir.config_parameter'].sudo()
        access = max(5, params.get_int('om_ai_mcp.oauth_access_minutes', 60))
        refresh = max(1, params.get_int('om_ai_mcp.oauth_refresh_days', 30))
        return timedelta(minutes=access), timedelta(days=refresh)

    def _issue_tokens(self, parent=None):
        """New access and refresh tokens (plain values are returned once, only
        their hashes are kept)."""
        self.ensure_one()
        access_life, refresh_life = self._lifetimes()
        now = fields.Datetime.now()
        access = ACCESS_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
        Token = self.env['om.mcp.oauth.token'].sudo()
        Token.create([
            {'grant_id': self.id, 'kind': 'access', 'token_hash': token_hash(access), 'expires': now + access_life},
            {'grant_id': self.id, 'kind': 'refresh', 'token_hash': token_hash(refresh), 'expires': now + refresh_life,
             'parent_id': parent and parent.id},
        ])
        self.sudo().write({'expires': now + refresh_life})
        return {
            'access_token': access,
            'token_type': 'Bearer',
            'expires_in': int(access_life.total_seconds()),
            'refresh_token': refresh,
            'scope': self.scope,
        }

    @api.model
    def _check_access_token(self, value):
        """Return the grant of a valid access token, else an empty recordset."""
        if not value or not value.startswith(ACCESS_PREFIX) or len(value) > 200:
            return self.browse()
        token = self.env['om.mcp.oauth.token'].sudo().search([
            ('token_hash', '=', token_hash(value)), ('kind', '=', 'access'),
            ('expires', '>', fields.Datetime.now()),
        ], limit=1)
        grant = token.grant_id
        if not grant or not grant.active or not grant.client_id._usable() or not grant.user_id.active:
            return self.browse()
        return grant

    @api.model
    def _cron_cleanup(self):
        now = fields.Datetime.now()
        self.env['om.mcp.oauth.token'].sudo().search([('expires', '<', now)], limit=50000).unlink()
        self.env['om.mcp.oauth.code'].sudo().search([('expires', '<', now)]).unlink()
        expired = self.sudo().search([('active', '=', True), ('expires', '<', now)])
        expired._revoke()
        limit_date = now - timedelta(days=90)
        self.sudo().with_context(active_test=False).search([
            ('active', '=', False), ('revoked', '<', limit_date)]).unlink()
        # apps that registered but were never used
        self.env['om.mcp.oauth.client'].sudo().search([
            ('registration', '=', 'dynamic'), ('grant_ids', '=', False),
            ('create_date', '<', now - timedelta(days=30)),
        ]).unlink()


class OmMcpOauthToken(models.Model):
    _name = 'om.mcp.oauth.token'
    _description = 'MCP OAuth Token'

    grant_id = fields.Many2one('om.mcp.oauth.grant', required=True, ondelete='cascade', index=True)
    kind = fields.Selection([('access', 'Access'), ('refresh', 'Refresh')], required=True)
    token_hash = fields.Char(required=True, index=True)
    expires = fields.Datetime(required=True, index=True)
    used = fields.Boolean(help='A refresh token that was exchanged already.')
    parent_id = fields.Many2one('om.mcp.oauth.token', ondelete='set null')

    _token_unique = models.Constraint('UNIQUE(token_hash)', 'Tokens must be unique.')


class OmMcpOauthCode(models.Model):
    """An authorization code: single use, short lived, bound to the app, the
    redirect URI, the PKCE challenge and the resource."""
    _name = 'om.mcp.oauth.code'
    _description = 'MCP OAuth Authorization Code'

    code_hash = fields.Char(required=True, index=True)
    client_id = fields.Many2one('om.mcp.oauth.client', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    redirect_uri = fields.Char(required=True)
    code_challenge = fields.Char(required=True)
    scope = fields.Char(required=True)
    resource = fields.Char(required=True)
    expires = fields.Datetime(required=True)
    used = fields.Boolean()
    grant_id = fields.Many2one('om.mcp.oauth.grant', ondelete='cascade')

    _code_unique = models.Constraint('UNIQUE(code_hash)', 'Codes must be unique.')

    @api.model
    def _new(self, client, user, redirect_uri, challenge, scope, resource):
        code = CODE_PREFIX + secrets.token_urlsafe(32)
        self.sudo().create({
            'code_hash': token_hash(code),
            'client_id': client.id,
            'user_id': user.id,
            'redirect_uri': redirect_uri,
            'code_challenge': challenge,
            'scope': scope,
            'resource': resource,
            'expires': fields.Datetime.now() + timedelta(seconds=CODE_SECONDS),
        })
        return code

    @api.model
    def _find(self, code):
        if not code or not isinstance(code, str) or not code.startswith(CODE_PREFIX) or len(code) > 200:
            return self.browse()
        return self.sudo().search(Domain('code_hash', '=', token_hash(code)), limit=1)
