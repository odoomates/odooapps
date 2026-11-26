import json

from markupsafe import Markup

from odoo import api, fields, models
from odoo.http import request
from odoo.http.router import db_list

from odoo.addons.base.models.res_users import check_identity


class OmMcpConnect(models.TransientModel):
    """How to connect an AI app: the endpoint and examples of client configs."""
    _name = 'om.mcp.connect'
    _description = 'Connect an AI App'

    endpoint = fields.Char(string='MCP Endpoint', compute='_compute_help')
    database = fields.Char(compute='_compute_help')
    enabled = fields.Boolean(compute='_compute_help')
    oauth_enabled = fields.Boolean(string='OAuth Sign-In', compute='_compute_help')
    key_count = fields.Integer(string='My MCP Keys', compute='_compute_help')
    examples = fields.Html(compute='_compute_help', sanitize=False)

    @api.depends_context('uid')
    def _compute_help(self):
        base_url = self.get_base_url().rstrip('/')
        endpoint = '%s/mcp' % base_url
        database = self.env.cr.dbname
        try:
            host = request.httprequest.environ.get('HTTP_HOST') if request else None
            several = len(db_list(force=True, host=host)) > 1
        except Exception:  # noqa: BLE001 - the list may be disabled
            several = True
        enabled = bool(self.env['ir.config_parameter'].sudo().get_bool('om_ai_mcp.enabled'))
        oauth_enabled = bool(self.env['ir.config_parameter'].sudo().get_bool('om_ai_mcp.oauth_enabled'))
        key_count = self.env['res.users.apikeys'].sudo().search_count([
            ('user_id', '=', self.env.uid), ('scope', 'in', ('mcp', 'mcp_read'))])
        examples = self._examples(endpoint, database if several else None, oauth_enabled)
        for wizard in self:
            wizard.endpoint = endpoint
            wizard.database = database
            wizard.enabled = enabled
            wizard.oauth_enabled = oauth_enabled
            wizard.key_count = key_count
            wizard.examples = examples

    def _examples(self, endpoint, database, oauth=False):
        key = '<your MCP key>'
        headers = {'Authorization': 'Bearer %s' % key}
        if database:
            headers['X-Odoo-Database'] = database
        remote_args = ['-y', 'mcp-remote', endpoint, '--header', 'Authorization:${ODOO_AUTH}']
        remote_env = {'ODOO_AUTH': 'Bearer %s' % key}
        if database:
            remote_args += ['--header', 'X-Odoo-Database:%s' % database]
        claude_desktop = {'mcpServers': {'odoo': {'command': 'npx', 'args': remote_args, 'env': remote_env}}}
        cursor = {'mcpServers': {'odoo': {'url': endpoint, 'headers': headers}}}
        vscode_headers = dict(headers, Authorization='Bearer ${input:odoo-mcp-key}')
        vscode = {
            'servers': {'odoo': {'type': 'http', 'url': endpoint, 'headers': vscode_headers}},
            'inputs': [{'type': 'promptString', 'id': 'odoo-mcp-key', 'description': 'Odoo MCP key',
                        'password': True}],
        }
        header_flags = ' '.join('--header "%s: %s"' % item for item in headers.items())
        claude_code = 'claude mcp add --transport http odoo %s %s' % (endpoint, header_flags)
        inspector = 'npx @modelcontextprotocol/inspector --cli %s --transport http --method tools/list %s' % (
            endpoint, header_flags)
        _ = self.env._
        sections = []
        if oauth:
            sections += [
                (_('Claude.ai, Claude Desktop and other apps with OAuth (no key)'),
                 _('Add a custom connector with this URL. The app opens Odoo: sign in, choose whether the app may '
                   'change data and allow it. Disconnect it in MCP Server > Connected Apps.'),
                 endpoint),
                (_('Claude Code with OAuth'),
                 _('Run in a terminal, then type /mcp in Claude Code and choose Authenticate:'),
                 'claude mcp add --transport http odoo %s' % endpoint),
            ]
        sections += [
            (_('Claude Desktop with a key'),
             _('Settings > Developer > Edit Config opens claude_desktop_config.json. The mcp-remote bridge '
               '(Node.js) forwards to the Odoo endpoint with your key. Restart Claude Desktop afterwards.'),
             json.dumps(claude_desktop, indent=2)),
            (_('Claude Code'), _('Run in a terminal:'), claude_code),
            (_('Cursor'), _('Add to ~/.cursor/mcp.json (or .cursor/mcp.json in a project):'),
             json.dumps(cursor, indent=2)),
            (_('VS Code'), _('Add to .vscode/mcp.json; VS Code asks for the key once and keeps it secret:'),
             json.dumps(vscode, indent=2)),
            (_('MCP Inspector'),
             _('Run npx @modelcontextprotocol/inspector, choose the Streamable HTTP transport, enter the URL and '
               'an Authorization header with Bearer and your key. Or list the tools from a terminal:'),
             inspector),
        ]
        parts = []
        for title, text, code in sections:
            parts.append(Markup('<h4 class="mt-4">%s</h4><p class="text-muted mb-1">%s</p>'
                                '<pre class="bg-light border rounded p-2 mb-0" style="white-space: pre-wrap;">'
                                '%s</pre>') % (title, text, code))
        return Markup('').join(parts)

    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = self.env._('Connect an AI App')

    @api.model
    def _action_open(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Connect an AI App'),
            'res_model': self._name,
            'res_id': self.create({}).id,
            'views': [(self.env.ref('om_ai_mcp.om_mcp_connect_view_form').id, 'form')],
            'target': 'current',
        }

    def _new_key(self, scope, name):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.users.apikeys.description',
            'name': self.env._('Create MCP Key'),
            'target': 'new',
            'views': [(False, 'form')],
            'context': {'default_scope': scope, 'default_name': name},
        }

    @check_identity
    def action_new_key(self):
        return self._new_key('mcp', 'MCP')

    @check_identity
    def action_new_read_key(self):
        return self._new_key('mcp_read', 'MCP read only')

    def action_my_keys(self):
        return self.env['ir.actions.act_window']._for_xml_id('om_ai_mcp.om_mcp_key_action')
