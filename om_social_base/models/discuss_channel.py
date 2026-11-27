from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DiscussChannel(models.Model):
    """ A conversation of the Social Inbox: the chat of an account with one
    customer, in Discuss. Its members are the users of the account, and the
    contact. What a user writes in it goes out on the channel. """
    _inherit = 'discuss.channel'

    channel_type = fields.Selection(
        selection_add=[('om_social', 'Social Conversation')], ondelete={'om_social': 'cascade'})
    om_social_account_id = fields.Many2one(
        'om.social.account', string='Social Account', index='btree_not_null', ondelete='cascade', readonly=True)
    om_social_address = fields.Char('Customer Address', readonly=True,
                                    help="The phone number or the handle of the customer.")
    om_social_identity_id = fields.Many2one(
        'om.social.identity', string='Customer Identity', index='btree_not_null', ondelete='set null', readonly=True,
        help="The customer in the channel: their user ID and username, which keep a conversation whose address the "
             "channel does not share.")
    om_social_partner_id = fields.Many2one('res.partner', string='Customer', ondelete='set null', readonly=True)
    om_social_last_incoming = fields.Datetime(
        'Last Message of the Customer', readonly=True,
        help="Some providers accept free text only within 24 hours of it, templates after.")
    om_social_profile_name = fields.Char('Profile Name', readonly=True,
                                         help="The name the customer gave themselves in the channel.")
    om_social_picture_date = fields.Datetime(
        'Picture Looked For', readonly=True, help="When the profile picture of the customer was last looked for.")
    om_social_res_model = fields.Char('Last Document Model', readonly=True)
    om_social_res_id = fields.Many2oneReference('Last Document ID', model_field='om_social_res_model', readonly=True)

    _om_social_address_unique = models.UniqueIndex(
        "(om_social_account_id, om_social_address) WHERE channel_type = 'om_social'")
    _om_social_identity_unique = models.UniqueIndex(
        "(om_social_account_id, om_social_identity_id) WHERE channel_type = 'om_social'")

    @api.model_create_multi
    def create(self, vals_list):
        """ A conversation is made by its account, on the first message:
        Discuss lets a user make chats they belong to, which would let anyone
        make the conversation of a customer and read it. """
        if not self.env.su:
            for vals in vals_list:
                self._om_social_check_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            self._om_social_check_values(vals)
            if 'channel_type' in vals and any(channel.channel_type == 'om_social' for channel in self):
                raise AccessError(_("A conversation of the Social Inbox stays one."))
        return super().write(vals)

    @api.depends('om_social_partner_id.image_128')
    def _compute_avatar_128(self):
        """ A conversation shows the photo of its contact, the one the channel
        gave too: the picture of an unknown customer is its own. """
        super()._compute_avatar_128()
        for channel in self.filtered(lambda c: c.channel_type == 'om_social' and not c.image_128):
            # sudo: the photo of the contact, which a user of the account may not read
            if photo := channel.om_social_partner_id.sudo().image_128:
                channel.avatar_128 = photo

    @api.model
    def _om_social_check_values(self, vals):
        if vals.get('channel_type') == 'om_social' or any(name.startswith('om_social_') for name in vals):
            raise AccessError(_("The conversations of the Social Inbox are made and kept by their account."))

    def _om_social_sync_members(self):
        """ The users of the account and the contact are members. """
        for channel in self:
            partners = channel.om_social_account_id.user_ids.partner_id | channel.om_social_partner_id
            missing = partners - channel.channel_member_ids.partner_id
            if missing:
                channel._add_members(partners=missing, post_joined_message=False)

    def _om_social_set_document(self, document):
        """ The conversation shows the document it last spoke about. """
        if document and document._name not in ('discuss.channel', 'res.partner'):
            self.write({'om_social_res_model': document._name, 'om_social_res_id': document.id})

    def _om_social_get_document(self):
        self.ensure_one()
        if not self.om_social_res_model or self.om_social_res_model not in self.env:
            return None
        return self.env[self.om_social_res_model].browse(self.om_social_res_id).exists() or None

    def _om_social_recipient(self):
        """ Where a message of this conversation goes: the address, else the
        user ID of the customer. """
        self.ensure_one()
        return self.om_social_address or self.om_social_identity_id.user_ref or False

    def _om_social_label(self):
        """ How the customer of a conversation without a contact is shown: the
        address, else the username, else the user ID. """
        self.ensure_one()
        return self.om_social_address or self.om_social_identity_id._om_social_label() or False

    def _om_social_is_of(self, partner):
        """ Whether ``partner`` is the customer of this conversation: their
        identity in it, else their address (channel modules extend this). """
        self.ensure_one()
        return bool(self.om_social_identity_id and self.om_social_identity_id.partner_id == partner)

    def _om_social_link_partner(self, partner):
        """ The contact of an unknown customer is made: the conversation is
        with them now, and so are its messages. """
        self.ensure_one()
        # the picture of the customer becomes the photo of a contact that has none
        if self.image_128 and not partner.image_1920:
            partner.sudo().image_1920 = self.image_128
        self.write({'om_social_partner_id': partner.id, 'name': partner.name, 'image_128': False})
        identity = self.om_social_identity_id
        if identity and identity.partner_id != partner:
            identity.sudo().partner_id = partner
        elif not identity and self.om_social_address:
            self.om_social_identity_id = self.env['om.social.identity']._om_social_get(
                self.om_social_account_id.channel, address=self.om_social_address, partner=partner)
        self._om_social_sync_members()
        self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', self.id), ('message_type', '=', 'om_social'),
            ('author_id', '=', False),
        ]).write({'author_id': partner.id, 'email_from': False})
        account = self.om_social_account_id
        self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_social'),
            *account._om_social_address_domain(self.om_social_address, identity.user_ref),
            ('res_partner_id', '=', False), ('mail_message_id.om_social_account_id', '=', account.id),
        ]).write({'res_partner_id': partner.id})

    def _om_social_merge_into(self, channel):
        """ The customer of this conversation, known by their user ID only, is
        the one of ``channel``, known by the address: its messages go there,
        and this one, empty, is archived (not deleted: the open pages may
        still be told about it in this transaction). """
        self.ensure_one()
        messages = self.env['mail.message'].sudo().search([('model', '=', 'discuss.channel'), ('res_id', '=', self.id)])
        messages.write({'res_id': channel.id})
        self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'discuss.channel'), ('res_id', '=', self.id), ('id', 'in', messages.attachment_ids.ids),
        ]).write({'res_id': channel.id})
        last = [date for date in (self.om_social_last_incoming, channel.om_social_last_incoming) if date]
        values = {'om_social_last_incoming': max(last, default=False)}
        if not channel.om_social_partner_id and self.om_social_partner_id:
            values['om_social_partner_id'] = self.om_social_partner_id.id
        identity = self.om_social_identity_id
        self.write({'active': False, 'om_social_identity_id': False, 'om_social_res_model': False,
                    'om_social_res_id': False})
        # the identity leaves this conversation before the other one takes it: one conversation each
        self.flush_recordset(['om_social_identity_id'])
        previous = channel.om_social_identity_id
        channel.write(dict(values, om_social_identity_id=identity.id))
        if previous and previous != identity:
            identity._om_social_learn(address=channel.om_social_address, username=previous.username,
                                      profile_name=previous.profile_name, partner_id=previous.partner_id.id)

    def om_social_action_create_contact(self):
        """ The form of a new contact with the address of this conversation;
        saving it links them. """
        self.ensure_one()
        self.om_social_account_id._om_social_check_user()
        identity = self.om_social_identity_id
        return {
            'type': 'ir.actions.act_window',
            'name': _("Create Contact"),
            'res_model': 'res.partner',
            'views': [(False, 'form')],
            'target': 'new',
            'context': dict(self._om_social_contact_defaults(), **{
                'default_name': self.om_social_profile_name or identity.username or self._om_social_recipient(),
                'om_social_channel_id': self.id,
            }),
        }

    def _om_social_contact_defaults(self):
        """ The values of the contact made from this conversation: channel
        modules add theirs (the phone number...). """
        return {}

    def om_social_action_open_document(self):
        self.ensure_one()
        document = self._om_social_get_document()
        if not document:
            raise UserError(_("This conversation is not about a document."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': document._name,
            'res_id': document.id,
            'views': [(False, 'form')],
        }

    # ------------------------------------------------------------
    # MESSAGING
    # ------------------------------------------------------------

    def message_post(self, *, message_type='notification', **kwargs):
        """ What a user writes in a conversation goes out on the channel. """
        if self.channel_type != 'om_social' or message_type != 'comment':
            return super().message_post(message_type=message_type, **kwargs)
        account = self.om_social_account_id
        account._om_social_check_user()
        account._om_social_check_free_text(self)
        message = super().message_post(message_type='om_social', om_social_account_id=account.id, **kwargs)
        notification = message._om_social_add_notification(self._om_social_recipient(), self.om_social_partner_id)
        # posted from Discuss, which runs no action: the page of the user does
        account._om_social_send_action(notification._om_social_send())
        return message

    def _notify_get_recipients(self, message, **kwargs):
        """ The users of a conversation get the messages of the customer as
        web push, as in a chat. """
        if self.channel_type != 'om_social' or message.message_type != 'om_social':
            return super()._notify_get_recipients(message, **kwargs)
        members = self.channel_member_ids.sudo().filtered(
            lambda m: m.partner_id != message.author_id and m.partner_id.user_ids and not m.mute_until_dt)
        return [{
            'active': True,
            'id': member.partner_id.id,
            'is_cc': False,
            'is_follower': False,
            'groups': [],
            'lang': member.partner_id.lang,
            'notif': 'web_push',
            'share': member.partner_id.partner_share,
            'type': 'user',
            'uid': member.partner_id.user_ids[:1].id,
            'ushare': False,
        } for member in members]

    def _store_channel_fields(self, res):
        super()._store_channel_fields(res)
        is_social = lambda channel: channel.channel_type == 'om_social'  # noqa: E731
        res.attr('om_social_address', predicate=is_social)
        res.attr('om_social_channel', lambda channel: channel.om_social_account_id.channel, predicate=is_social)
        res.attr('om_social_has_contact', lambda channel: bool(channel.om_social_partner_id), predicate=is_social)
        res.attr('om_social_provider', lambda channel: channel.om_social_account_id.provider, predicate=is_social)
        res.attr('om_social_free_text_until',
                 lambda channel: fields.Datetime.to_string(channel.om_social_account_id._om_social_free_text_until(channel)),
                 predicate=is_social)
        # sudo: the users of the conversation see the name of the document it speaks about
        res.attr(
            'om_social_document_name',
            lambda channel: (document := channel._om_social_get_document()) and document.sudo().display_name or False,
            predicate=is_social,
        )


class OmSocialAccount(models.Model):
    _inherit = 'om.social.account'

    def _om_social_get_channel(self, address, partner=False, profile_name=False, user_ref=False, username=False):
        """ The conversation of this account with ``address``, or with the
        customer of the user ID ``user_ref`` when the channel does not share
        their address, made on the first message. A conversation known by one
        of them learns the other; two conversations of the same customer
        become one. Without a contact, it is named by the address (or the
        username, or the user ID), and the name the customer gave themselves
        in the channel. """
        self.ensure_one()
        address = self._om_social_clean_address(address) or False
        Channel = self.env['discuss.channel'].sudo()
        domain = [('channel_type', '=', 'om_social'), ('om_social_account_id', '=', self.id)]
        by_address = Channel.search([*domain, ('om_social_address', '=', address)], limit=1) if address else Channel
        by_user = Channel.search([*domain, ('om_social_identity_id.user_ref', '=', user_ref)], limit=1) \
            if user_ref else Channel
        if by_address and by_user and by_address != by_user:
            if by_user.om_social_address:
                # the user ID moved to another address: the conversation of the address takes it
                by_user.write({'om_social_identity_id': False})
                by_user.flush_recordset(['om_social_identity_id'])
            else:
                by_user._om_social_merge_into(by_address)
        channel = by_address or by_user
        learned = False
        if channel and address and not channel.om_social_address:
            channel.om_social_address = address
            learned = True
        Identity = self.env['om.social.identity']
        if channel:
            identity = channel.om_social_identity_id
            if not identity or (user_ref and identity.user_ref and identity.user_ref != user_ref):
                # a conversation known by its address only, or a new user ID for it: its identity
                learned = learned or bool(user_ref or username)
                values = {'address': channel.om_social_address, 'user_ref': user_ref, 'username': username,
                          'profile_name': channel.om_social_profile_name,
                          'partner': partner or channel.om_social_partner_id}
                identity = Identity._om_social_get(self.channel, **values)
                if Channel.search_count([*domain, ('om_social_identity_id', '=', identity.id)], limit=1):
                    # the identity of another conversation of the account: this one gets its own
                    identity = Identity.sudo().create({
                        'channel': self.channel, 'address': values['address'], 'user_ref': user_ref or False,
                        'username': username or False, 'profile_name': values['profile_name'] or False,
                        'partner_id': values['partner'].id or False,
                    })
                channel.om_social_identity_id = identity
            else:
                learned = learned or bool(user_ref and identity.user_ref != user_ref
                                          or username and identity.username != username)
                identity._om_social_learn(address=channel.om_social_address, user_ref=user_ref, username=username)
        profile_name = profile_name or channel.om_social_profile_name
        if channel:
            label = channel._om_social_label()
        else:
            label = address or (f'@{username}' if username else user_ref)
        name = partner.name if partner else (f'{profile_name} ({label})' if profile_name else label)
        if not channel:
            identity = Identity._om_social_get(
                self.channel, address=address, user_ref=user_ref, username=username, profile_name=profile_name,
                partner=partner)
            members = self.user_ids.partner_id | (partner or self.env['res.partner'])
            channel = Channel.create({
                'name': name,
                'channel_type': 'om_social',
                'om_social_account_id': self.id,
                'om_social_address': address,
                'om_social_identity_id': identity.id,
                'om_social_partner_id': partner.id if partner else False,
                'om_social_profile_name': profile_name or False,
                'channel_partner_ids': [Command.link(p.id) for p in members],
            })
            # Discuss adds whoever makes a channel: only the users of the account belong here
            channel.channel_member_ids.filtered(lambda m: m.partner_id not in members).unlink()
        elif partner and channel.om_social_partner_id != partner:
            channel._om_social_link_partner(partner)
        elif not partner and profile_name and profile_name != channel.om_social_profile_name:
            # a conversation with a contact keeps the name of the contact
            channel.write({'om_social_profile_name': profile_name,
                           **({} if channel.om_social_partner_id else {'name': name})})
            channel.om_social_identity_id._om_social_learn(profile_name=profile_name)
        elif not partner and not channel.om_social_partner_id and learned and name != channel.name:
            # named by the address now, or by the new username
            channel.name = name
        channel._om_social_sync_members()
        return channel
