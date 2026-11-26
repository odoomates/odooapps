from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_ai_chat_model_id = fields.Many2one('om.ai.model', string='AI Chat Model', domain=[('cap_chat', '=', True)])
    om_ai_fast_model_id = fields.Many2one('om.ai.model', string='AI Fast Model', domain=[('cap_chat', '=', True)])
    om_ai_vision_model_id = fields.Many2one('om.ai.model', string='AI Vision Model',
                                            domain=[('cap_vision', '=', True)])
    om_ai_embeddings_model_id = fields.Many2one('om.ai.model', string='AI Embeddings Model',
                                                domain=[('cap_embeddings', '=', True)])
    om_ai_user_daily_tokens = fields.Integer(string='AI Tokens per User per Day')
    om_ai_user_daily_cost = fields.Float(string='AI Cost per User per Day (USD)', digits=(16, 4))
    om_ai_company_daily_tokens = fields.Integer(string='AI Tokens per Company per Day')
    om_ai_company_daily_cost = fields.Float(string='AI Cost per Company per Day (USD)', digits=(16, 4))
    om_ai_log_content = fields.Boolean(string='Log AI Requests and Answers')
    om_ai_editor_provider = fields.Boolean(string='Editor Text Generation with Own Provider')
    om_ai_assistant_tools = fields.Boolean(string='AI Assistant Looks Up Records', default=True)
