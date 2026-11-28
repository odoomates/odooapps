from odoo import models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _om_ai_conversation(self):
        self.ensure_one()
        return self.env['om.ai.whatsapp.conversation'].sudo().search([('channel_id', '=', self.id)], limit=1)

    def _om_ai_state(self):
        """ ai, human, stopped, or False when no assistant works on this number. """
        self.ensure_one()
        if self.channel_type != 'om_social' or not self.sudo().om_social_account_id.om_ai_active:
            return False
        conversation = self._om_ai_conversation()
        return conversation.state if conversation else 'ai'

    def om_ai_whatsapp_action_take_over(self):
        self.ensure_one()
        self.om_social_account_id._om_social_check_user()
        conversation = self.env['om.ai.whatsapp.conversation'].sudo()._om_ai_get(self.sudo())
        conversation._om_ai_take_over(self.env.user)
        return self._om_ai_state()

    def om_ai_whatsapp_action_give_back(self):
        self.ensure_one()
        self.om_social_account_id._om_social_check_user()
        conversation = self.env['om.ai.whatsapp.conversation'].sudo()._om_ai_get(self.sudo())
        conversation._om_ai_give_back(self.env.user)
        return self._om_ai_state()

    def message_post(self, *, message_type='notification', **kwargs):
        """ A user who writes to the customer takes over from the assistant. """
        message = super().message_post(message_type=message_type, **kwargs)
        if (self.channel_type == 'om_social' and message_type == 'comment'
                and not self.env.context.get('om_ai_whatsapp_sending') and not self.env.user.om_ai_whatsapp_assistant
                and not self.env.user.share and self.sudo().om_social_account_id.om_ai_active):
            conversation = self._om_ai_conversation()
            if conversation and conversation.state == 'ai':
                conversation._om_ai_take_over(self.env.user)
        return message

    def _store_channel_fields(self, res):
        super()._store_channel_fields(res)
        res.attr('om_ai_whatsapp_state', lambda channel: channel._om_ai_state(),
                 predicate=lambda channel: channel.channel_type == 'om_social')
