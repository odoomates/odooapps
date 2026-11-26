from datetime import timedelta

from odoo import api, fields, models


class OmAiUsage(models.Model):
    _name = 'om.ai.usage'
    _description = 'AI Usage'
    _order = 'id desc'
    _rec_name = 'feature'

    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    user_id = fields.Many2one('res.users', string='User', index=True, ondelete='set null')
    company_id = fields.Many2one('res.company', string='Company', index=True, ondelete='cascade')
    feature = fields.Char(index=True)
    provider_id = fields.Many2one('om.ai.provider', string='Provider', ondelete='set null')
    model_id = fields.Many2one('om.ai.model', string='Model', ondelete='set null')
    model_name = fields.Char(string='Model ID')
    prompt_tokens = fields.Integer(string='Prompt Tokens', aggregator='sum')
    completion_tokens = fields.Integer(string='Completion Tokens', aggregator='sum')
    total_tokens = fields.Integer(string='Total Tokens', aggregator='sum')
    cost = fields.Float(string='Estimated Cost (USD)', digits=(16, 6), aggregator='sum')
    duration = fields.Float(string='Duration (s)', digits=(16, 2), aggregator='avg')
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('blocked', 'Blocked by Limit'),
    ], default='success', required=True, index=True)
    error = fields.Text()
    request_text = fields.Text(string='Request')
    response_text = fields.Text(string='Response')

    @api.model
    def _get_daily_totals(self, user=None, company=None):
        """Tokens and cost of the successful calls since midnight (UTC)."""
        start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        domain = [('date', '>=', start), ('status', '=', 'success')]
        if user:
            domain.append(('user_id', '=', user.id))
        if company:
            domain.append(('company_id', '=', company.id))
        [(tokens, cost)] = self.sudo()._read_group(domain, aggregates=['total_tokens:sum', 'cost:sum'])
        return tokens or 0, cost or 0.0

    @api.model
    def _cron_cleanup(self):
        days = self.env['ir.config_parameter'].sudo().get_int('om_ai.usage_keep_days', 365)
        if days > 0:
            self.sudo().search([('date', '<', fields.Datetime.now() - timedelta(days=days))], limit=10000).unlink()
