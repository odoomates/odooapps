from markupsafe import Markup

from odoo import models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _message_post_after_hook(self, message):
        res = super()._message_post_after_hook(message)
        self._om_ai_handle_message(message)
        return res

    def _om_ai_handle_message(self, message):
        partner = self.env.ref('om_ai.partner_ai_assistant', raise_if_not_found=False)
        if not partner or message.message_type != 'comment' or message.author_id == partner:
            return
        for channel in self:
            in_chat = channel.channel_type == 'chat' and partner in channel.channel_member_ids.partner_id
            if not in_chat and partner not in message.partner_ids:
                continue
            user = self.env.user
            if message.author_id != user.partner_id:
                continue
            if not user.has_group('om_ai.group_ai_user'):
                channel.sudo().message_post(
                    author_id=partner.id,
                    body=Markup('<p><i>%s</i></p>') % self.env._(
                        'You are not allowed to use the AI Assistant. Ask your administrator for the AI / User access.'),
                    message_type='comment',
                    silent=True,
                    subtype_xmlid='mail.mt_comment',
                )
                continue
            self.env['om.ai.chat.job'].sudo().create({
                'channel_id': channel.id,
                'message_id': message.id,
                'user_id': user.id,
                'company_id': self.env.company.id,
            })
            channel.sudo().channel_member_ids.filtered(lambda m: m.partner_id == partner)._notify_typing(True)
            self.env.ref('om_ai.ir_cron_om_ai_chat').sudo()._trigger()
