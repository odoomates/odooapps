from odoo import fields, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    om_ai_agent_id = fields.Many2one('om.ai.livechat.agent', string='AI Agent', index='btree_not_null',
                                     ondelete='set null', readonly=True)
    om_ai_handed_over = fields.Boolean(string='Handed Over by AI', readonly=True)

    def _message_post_after_hook(self, message):
        res = super()._message_post_after_hook(message)
        self._om_ai_livechat_handle(message)
        return res

    def _om_ai_livechat_handle(self, message):
        for channel in self.filtered(lambda c: c.channel_type == 'livechat'):
            channel_sudo = channel.sudo()
            agent = channel_sudo.om_ai_agent_id
            if not agent or not agent.active or message.message_type != 'comment' or channel_sudo.livechat_end_dt:
                continue
            if message.author_id == agent.partner_id:
                continue
            bot_member = channel_sudo.channel_member_ids.filtered(lambda m: m.partner_id == agent.partner_id)
            if not bot_member:
                continue
            # an operator in the chat answers from now on
            if channel_sudo.livechat_agent_history_ids:
                continue
            visitor = channel_sudo.livechat_customer_history_ids
            is_visitor = (message.author_guest_id and message.author_guest_id in visitor.guest_id) or (
                message.author_id and message.author_id in visitor.partner_id)
            if not is_visitor:
                continue
            self.env['om.ai.livechat.job'].sudo().create({
                'channel_id': channel.id,
                'message_id': message.id,
                'agent_id': agent.id,
                'company_id': agent.company_id.id,
            })
            bot_member._notify_typing(True)
            self.env.ref('om_ai_livechat.ir_cron_om_ai_livechat').sudo()._trigger()
