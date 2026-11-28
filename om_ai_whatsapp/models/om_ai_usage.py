from odoo import fields, models


class OmAiUsage(models.Model):
    _inherit = 'om.ai.usage'

    om_ai_whatsapp_conversation_id = fields.Many2one(
        'om.ai.whatsapp.conversation', string='WhatsApp Conversation', index='btree_not_null', ondelete='set null')
