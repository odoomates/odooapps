from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_ai_mcp_enabled = fields.Boolean(string='MCP Server', config_parameter='om_ai_mcp.enabled')
    om_ai_mcp_rate_limit = fields.Integer(string='MCP Requests per Window', config_parameter='om_ai_mcp.rate_limit',
                                          default=120)
    om_ai_mcp_rate_window = fields.Integer(string='MCP Rate Window (seconds)', config_parameter='om_ai_mcp.rate_window',
                                           default=60)
    om_ai_mcp_batch_limit = fields.Integer(string='MCP Records per Call', config_parameter='om_ai_mcp.batch_limit',
                                           default=20)
    om_ai_mcp_log_keep_days = fields.Integer(string='Keep MCP Logs (days)', config_parameter='om_ai_mcp.log_keep_days',
                                             default=90)
    om_ai_mcp_allowed_origins = fields.Char(string='MCP Allowed Origins', config_parameter='om_ai_mcp.allowed_origins',
                                            help='Browser origins allowed to call the MCP server, separated by commas, '
                                                 'e.g. http://localhost:6274. Apps that are not browsers send no '
                                                 'origin and are always allowed.')
    om_ai_mcp_instructions = fields.Char(string='MCP Instructions', config_parameter='om_ai_mcp.instructions',
                                         help='Extra instructions sent to the AI apps when they connect.')
    om_ai_mcp_oauth_enabled = fields.Boolean(string='MCP OAuth Sign-In', config_parameter='om_ai_mcp.oauth_enabled')
    om_ai_mcp_oauth_registration = fields.Boolean(string='MCP App Registration',
                                                  config_parameter='om_ai_mcp.oauth_registration')
    om_ai_mcp_oauth_registration_approval = fields.Boolean(
        string='Approve Registered Apps', config_parameter='om_ai_mcp.oauth_registration_approval',
        help='Apps that register themselves wait until an administrator approves them.')
    om_ai_mcp_oauth_access_minutes = fields.Integer(string='MCP Access Token Minutes', default=60,
                                                    config_parameter='om_ai_mcp.oauth_access_minutes')
    om_ai_mcp_oauth_refresh_days = fields.Integer(string='MCP Connection Days', default=30,
                                                  config_parameter='om_ai_mcp.oauth_refresh_days')
