from markupsafe import Markup

from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._om_ai_ensure_chat()
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'group_ids' in vals:
            self._om_ai_ensure_chat()
        return res

    def _om_ai_ensure_chat(self):
        """Open a chat with the AI Assistant for internal users who may use AI."""
        partner = self.env.ref('om_ai.partner_ai_assistant', raise_if_not_found=False)
        if not partner:
            return
        Channel = self.env['discuss.channel'].sudo()
        for user in self.filtered(lambda u: not u.share and u.active and u.has_group('om_ai.group_ai_user')):
            if Channel.search_count([
                ('channel_type', '=', 'chat'),
                ('channel_member_ids.partner_id', '=', partner.id),
                ('channel_member_ids.partner_id', '=', user.partner_id.id),
            ], limit=1):
                continue
            channel = Channel.with_user(user).with_context(mail_create_nosubscribe=True)._get_or_create_chat(
                [partner.id])
            channel.sudo().message_post(
                author_id=partner.id,
                body=Markup('<p>%s</p><p>%s</p>') % (
                    self.env._('Hello, I am your AI Assistant.'),
                    self.env._('Ask me anything, for example: "How many customers do we have in Belgium?" '
                               'I only look at records you are allowed to see.'),
                ),
                message_type='comment',
                silent=True,
                subtype_xmlid='mail.mt_comment',
            )

    def _om_ai_open_assistant(self):
        """Open the user's chat with the AI Assistant in Discuss."""
        self.ensure_one()
        self._om_ai_ensure_chat()
        partner = self.env.ref('om_ai.partner_ai_assistant')
        channel = self.env['discuss.channel'].with_user(self)._get_or_create_chat([partner.id])
        return {
            'type': 'ir.actions.client',
            'tag': 'mail.action_discuss',
            'name': self.env._('AI Assistant'),
            'params': {'active_id': 'discuss.channel_%s' % channel.id},
        }
