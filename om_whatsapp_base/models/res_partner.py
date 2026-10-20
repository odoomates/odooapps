from odoo import _, api, fields, models


class ResPartner(models.Model):
    _name = 'res.partner'
    # the sanitized number the WhatsApp messages are matched on, as the SMS app does
    _inherit = ['mail.thread.phone', 'res.partner']
    # a user who can read a contact can send it a WhatsApp, as later versions of Odoo allow
    _mail_post_access = 'read'

    om_whatsapp_message_count = fields.Integer(
        'WhatsApp Messages', compute='_compute_om_whatsapp_message_count',
        groups='om_whatsapp_base.group_om_whatsapp_user')

    @api.model_create_multi
    def create(self, vals_list):
        """ A contact made from an unknown WhatsApp conversation is linked to
        it: the one with its number, not a company made along. """
        partners = super().create(vals_list)
        if channel_id := self.env.context.get('om_whatsapp_channel_id'):
            channel = self.env['discuss.channel'].sudo().browse(channel_id).exists()
            partner = partners.filtered(lambda p: p.phone_sanitized == channel.om_whatsapp_number)[:1]
            if channel and partner and not channel.om_whatsapp_partner_id:
                channel._om_whatsapp_link_partner(partner)
        return partners

    def _om_whatsapp_channels(self):
        return self.env['discuss.channel'].search(
            [('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_partner_id', 'in', self.ids)])

    def _compute_om_whatsapp_message_count(self):
        """ The messages of the WhatsApp conversations with the contact: all
        of them are there, sent from a document, Discuss or the phone. """
        counts = dict(self.env['mail.message']._read_group(
            [('message_type', '=', 'om_whatsapp'), ('model', '=', 'discuss.channel'),
             ('res_id', 'in', self._om_whatsapp_channels().ids)],
            ['res_id'], ['__count']))
        channels = self._om_whatsapp_channels()
        for partner in self:
            partner.om_whatsapp_message_count = sum(
                counts.get(channel.id, 0) for channel in channels if channel.om_whatsapp_partner_id == partner)

    def action_om_whatsapp_messages(self):
        """ Open the conversation with the contact in Discuss. """
        self.ensure_one()
        channels = self._om_whatsapp_channels()
        if len(channels) == 1:
            return channels.open_chat_window_action()
        action = self.env['ir.actions.act_window']._for_xml_id('om_whatsapp_base.om_whatsapp_message_action')
        action['domain'] = [('message_type', '=', 'om_whatsapp'), ('model', '=', 'discuss.channel'), ('res_id', 'in', channels.ids)]
        action['context'] = {}
        return action

    def action_om_whatsapp_send(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Send WhatsApp"),
            'res_model': 'om.whatsapp.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_ids': self.ids, 'active_id': self.id},
        }
