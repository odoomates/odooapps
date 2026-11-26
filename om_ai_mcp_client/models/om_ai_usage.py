from odoo import fields, models


class OmAiUsage(models.Model):
    _inherit = 'om.ai.usage'

    mcp_remote_id = fields.Many2one('om.ai.mcp.remote', string='Outside MCP Server', ondelete='set null',
                                    index='btree_not_null')
    mcp_tool = fields.Char(string='Outside Tool')
