from odoo import api, models


class OmAi(models.AbstractModel):
    _inherit = 'om.ai'

    @api.model
    def _ai_log(self, vals, separate=False):
        if conversation_id := self.env.context.get('om_ai_whatsapp_conversation_id'):
            vals = dict(vals, om_ai_whatsapp_conversation_id=conversation_id)
        return super()._ai_log(vals, separate=separate)
