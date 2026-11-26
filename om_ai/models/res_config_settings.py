from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_ai_chat_model_id = fields.Many2one(related='company_id.om_ai_chat_model_id', readonly=False)
    om_ai_fast_model_id = fields.Many2one(related='company_id.om_ai_fast_model_id', readonly=False)
    om_ai_vision_model_id = fields.Many2one(related='company_id.om_ai_vision_model_id', readonly=False)
    om_ai_embeddings_model_id = fields.Many2one(related='company_id.om_ai_embeddings_model_id', readonly=False)
    om_ai_user_daily_tokens = fields.Integer(related='company_id.om_ai_user_daily_tokens', readonly=False)
    om_ai_user_daily_cost = fields.Float(related='company_id.om_ai_user_daily_cost', readonly=False)
    om_ai_company_daily_tokens = fields.Integer(related='company_id.om_ai_company_daily_tokens', readonly=False)
    om_ai_company_daily_cost = fields.Float(related='company_id.om_ai_company_daily_cost', readonly=False)
    om_ai_log_content = fields.Boolean(related='company_id.om_ai_log_content', readonly=False)
    om_ai_editor_provider = fields.Boolean(related='company_id.om_ai_editor_provider', readonly=False)
    om_ai_assistant_tools = fields.Boolean(related='company_id.om_ai_assistant_tools', readonly=False)
    om_ai_usage_keep_days = fields.Integer(string='Keep AI Usage Logs (days)', config_parameter='om_ai.usage_keep_days',
                                           default=365)
    om_ai_tool_batch_limit = fields.Integer(string='Records per AI Tool Call', config_parameter='om_ai.tool_batch_limit',
                                            default=20)
    om_ai_tool_attachment_kb = fields.Integer(string='AI Attachment Size Limit (KB)',
                                              config_parameter='om_ai.tool_attachment_kb', default=1024)
