from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    om_social_identity_ids = fields.One2many(
        'om.social.identity', 'partner_id', string='Social Identities', groups='base.group_user',
        help="The contact in the messaging channels: their user ID and username, which find them when a message "
             "comes in.")
    om_social_message_count = fields.Integer(
        'Social Messages', compute='_compute_om_social_message_count',
        groups='om_social_base.group_om_social_user')

    @api.model_create_multi
    def create(self, vals_list):
        """ A contact made from the conversation of an unknown customer is
        linked to it: the one of that customer, not a company made along. """
        partners = super().create(vals_list)
        if channel_id := self.env.context.get('om_social_channel_id'):
            channel = self.env['discuss.channel'].sudo().browse(channel_id).exists()
            if channel and not channel.om_social_partner_id:
                partner = partners.filtered(lambda p: channel._om_social_is_of(p))[:1]
                if not partner and not channel.om_social_address:
                    # known by a user ID only: nothing on the contact says it is them, but the form was theirs
                    partner = partners.filtered(lambda p: not p.is_company)[:1]
                if partner:
                    channel._om_social_link_partner(partner)
        return partners

    def _om_social_channels(self):
        return self.env['discuss.channel'].search(
            [('channel_type', '=', 'om_social'), ('om_social_partner_id', 'in', self.ids)])

    def _compute_om_social_message_count(self):
        """ The messages of the conversations with the contact: all of them
        are there, sent from a document, Discuss or the phone. """
        channels = self._om_social_channels()
        counts = dict(self.env['mail.message']._read_group(
            [('message_type', '=', 'om_social'), ('model', '=', 'discuss.channel'), ('res_id', 'in', channels.ids)],
            ['res_id'], ['__count']))
        for partner in self:
            partner.om_social_message_count = sum(
                counts.get(channel.id, 0) for channel in channels if channel.om_social_partner_id == partner)

    def action_om_social_messages(self):
        """ Open the conversation with the contact in Discuss. """
        self.ensure_one()
        channels = self._om_social_channels()
        if len(channels) == 1:
            return channels.open_chat_window_action()
        action = self.env['ir.actions.act_window']._for_xml_id('om_social_base.om_social_message_action')
        action['domain'] = [('message_type', '=', 'om_social'), ('model', '=', 'discuss.channel'),
                            ('res_id', 'in', channels.ids)]
        action['context'] = {}
        return action
