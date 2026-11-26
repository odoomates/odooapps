from datetime import timedelta

from odoo import api, fields, models


class OmMcpLog(models.Model):
    """One request of an MCP client. Written in its own transaction, so calls
    that fail are logged too."""
    _name = 'om.mcp.log'
    _description = 'MCP Call Log'
    _order = 'id desc'
    _rec_name = 'method'

    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    user_id = fields.Many2one('res.users', string='User', index=True, ondelete='set null')
    company_id = fields.Many2one('res.company', string='Company', ondelete='set null')
    key_id = fields.Integer(string='Key ID', index=True)
    key_name = fields.Char(string='Key')
    key_scope = fields.Selection([('mcp', 'Read and write'), ('mcp_read', 'Read only')], string='Key Access')
    auth_type = fields.Selection([('key', 'MCP Key'), ('oauth', 'OAuth App')], string='Signed In With',
                                 default='key')
    grant_id = fields.Many2one('om.mcp.oauth.grant', string='Connected App', ondelete='set null',
                               index='btree_not_null')
    session_id = fields.Many2one('om.mcp.session', string='Session', ondelete='set null', index='btree_not_null')
    client_name = fields.Char(string='Client')
    method = fields.Char(index=True)
    tool = fields.Char(index=True)
    target = fields.Char(string='Resource or Prompt')
    model = fields.Char(string='Model')
    duration = fields.Float(string='Duration (ms)', digits=(16, 1), aggregator='avg')
    status = fields.Selection([
        ('success', 'Success'),
        ('tool_error', 'Tool Error'),
        ('denied', 'Denied'),
        ('rate_limited', 'Rate Limited'),
        ('error', 'Error'),
    ], default='success', required=True, index=True)
    error = fields.Text()
    ip = fields.Char(string='IP Address')

    _key_date_index = models.Index('(key_id, date)')
    _grant_date_index = models.Index('(grant_id, date)')

    @api.model
    def _count_recent(self, key_id, seconds, grant_id=None):
        """Requests of a key (or of a connected app) in the last seconds; the
        rate-limited ones do not count."""
        since = fields.Datetime.now() - timedelta(seconds=seconds)
        owner = ('grant_id', '=', grant_id) if grant_id else ('key_id', '=', key_id)
        return self.sudo().search_count([owner, ('date', '>=', since), ('status', '!=', 'rate_limited')])

    @api.model
    def _cron_cleanup(self):
        days = self.env['ir.config_parameter'].sudo().get_int('om_ai_mcp.log_keep_days', 90)
        if days > 0:
            limit_date = fields.Datetime.now() - timedelta(days=days)
            self.sudo().search([('date', '<', limit_date)], limit=50000).unlink()
            self.env['om.mcp.session'].sudo().search([('last_activity', '<', limit_date)]).unlink()
