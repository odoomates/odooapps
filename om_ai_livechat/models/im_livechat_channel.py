from odoo import fields, models


class Im_LivechatChannel(models.Model):
    _inherit = 'im_livechat.channel'

    om_ai_agent_id = fields.Many2one('om.ai.livechat.agent', string='AI Agent', index='btree_not_null',
                                     ondelete='set null',
                                     help='The AI agent that answers the visitors of this channel.')
    om_ai_agent_mode = fields.Selection([
        ('always', 'Always, Operators Take Over When Needed'),
        ('no_operator', 'Only When No Operator Is Available'),
    ], string='AI Agent Answers', default='always', required=True)

    def _om_ai_agent_applies(self, operator_partner):
        self.ensure_one()
        agent = self.sudo().om_ai_agent_id
        if not agent or not agent.active or not agent.partner_id:
            return False
        return self.om_ai_agent_mode == 'always' or not operator_partner

    def _get_operator_info(self, /, **kwargs):
        info = super()._get_operator_info(**kwargs)
        if info['operator_model'] == 'chatbot.script' or not self._om_ai_agent_applies(info['operator_partner']):
            return info
        agent = self.sudo().om_ai_agent_id
        return dict(
            info,
            agent=self.env['res.users'],
            operator_partner=agent.partner_id,
            operator_model='om.ai.livechat.agent',
            om_ai_agent=agent,
        )

    def _get_livechat_discuss_channel_vals(self, /, **kwargs):
        vals = super()._get_livechat_discuss_channel_vals(**kwargs)
        if kwargs.get('operator_model') == 'om.ai.livechat.agent' and kwargs.get('om_ai_agent'):
            vals['om_ai_agent_id'] = kwargs['om_ai_agent'].id
        return vals

    def _get_channel_name(self, /, **kwargs):
        if kwargs.get('operator_model') == 'om.ai.livechat.agent' and kwargs.get('om_ai_agent'):
            visitor = kwargs.get('visitor_user')
            guest = kwargs.get('guest')
            names = [visitor.display_name if visitor else guest.name if guest else '', kwargs['om_ai_agent'].name]
            return ' '.join(filter(None, names))
        return super()._get_channel_name(**kwargs)

    def _is_livechat_available(self):
        return super()._is_livechat_available() or bool(self.sudo().om_ai_agent_id.active)
