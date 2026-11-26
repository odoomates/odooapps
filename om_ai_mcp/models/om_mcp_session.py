import hashlib

from odoo import fields, models


class OmMcpSession(models.Model):
    """A session opened by an MCP client with initialize. Only a hash of the
    session id is kept."""
    _name = 'om.mcp.session'
    _description = 'MCP Session'
    _order = 'last_activity desc, id desc'
    _rec_name = 'client_name'

    token_hash = fields.Char(required=True, index=True, copy=False)
    user_id = fields.Many2one('res.users', string='User', required=True, index=True, ondelete='cascade')
    key_id = fields.Integer(string='Key ID', index=True)
    key_name = fields.Char(string='Key')
    grant_id = fields.Many2one('om.mcp.oauth.grant', string='Connected App', ondelete='cascade',
                               index='btree_not_null')
    protocol_version = fields.Char()
    client_name = fields.Char(string='Client')
    client_version = fields.Char()
    last_activity = fields.Datetime(default=fields.Datetime.now, index=True)
    active = fields.Boolean(default=True)
    log_ids = fields.One2many('om.mcp.log', 'session_id', string='Calls')
    log_count = fields.Integer(compute='_compute_log_count', string='Calls Count')

    _token_unique = models.Constraint('UNIQUE(token_hash)', 'The session id must be unique.')

    @staticmethod
    def _hash(token):
        return hashlib.sha256((token or '').encode()).hexdigest()

    def _compute_log_count(self):
        counts = dict(self.env['om.mcp.log']._read_group([('session_id', 'in', self.ids)], ['session_id'],
                                                         ['__count']))
        for session in self:
            session.log_count = counts.get(session, 0)

    def action_end(self):
        self.write({'active': False})

    def action_view_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_ai_mcp.om_mcp_log_action')
        action['domain'] = [('session_id', '=', self.id)]
        action['context'] = {}
        return action
