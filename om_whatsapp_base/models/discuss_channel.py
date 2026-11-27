from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError


class DiscussChannel(models.Model):
    """ A WhatsApp conversation: the chat of an account with one number, in
    Discuss. Its members are the users of the account, and the contact. What
    a user writes in it goes out on WhatsApp. """
    _inherit = 'discuss.channel'

    channel_type = fields.Selection(
        selection_add=[('om_whatsapp', 'WhatsApp Conversation')], ondelete={'om_whatsapp': 'cascade'})
    om_whatsapp_account_id = fields.Many2one(
        'om.whatsapp.account', string='WhatsApp Account', index='btree_not_null', ondelete='cascade', readonly=True)
    om_whatsapp_number = fields.Char('WhatsApp Number', readonly=True)
    om_whatsapp_user_id = fields.Char(
        'WhatsApp User ID', readonly=True,
        help="The id WhatsApp gives the customer for your business: the conversation of a customer whose number "
             "WhatsApp does not share is kept by it.")
    om_whatsapp_username = fields.Char('WhatsApp Username', readonly=True,
                                       help="The username the customer chose in WhatsApp.")
    om_whatsapp_partner_id = fields.Many2one('res.partner', string='WhatsApp Contact', ondelete='set null', readonly=True)
    om_whatsapp_last_incoming = fields.Datetime(
        'Last Message of the Contact', readonly=True,
        help="Some providers accept free text only within 24 hours of it, templates after.")
    om_whatsapp_profile_name = fields.Char('WhatsApp Profile Name', readonly=True,
                                          help="The name the contact gave themselves in WhatsApp.")
    om_whatsapp_picture_date = fields.Datetime(
        'Picture Looked For', readonly=True, help="When the WhatsApp profile picture of the number was last looked for.")
    om_whatsapp_res_model = fields.Char('Last Document Model', readonly=True)
    om_whatsapp_res_id = fields.Many2oneReference('Last Document ID', model_field='om_whatsapp_res_model', readonly=True)

    _om_whatsapp_number_unique = models.UniqueIndex(
        "(om_whatsapp_account_id, om_whatsapp_number) WHERE channel_type = 'om_whatsapp'")
    _om_whatsapp_user_id_unique = models.UniqueIndex(
        "(om_whatsapp_account_id, om_whatsapp_user_id) WHERE channel_type = 'om_whatsapp'")

    @api.model_create_multi
    def create(self, vals_list):
        """ A conversation is made by its account, on the first message:
        Discuss lets a user make chats they belong to, which would let anyone
        make the conversation of a number and read it. """
        if not self.env.su:
            for vals in vals_list:
                self._om_whatsapp_check_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            self._om_whatsapp_check_values(vals)
            if 'channel_type' in vals and any(channel.channel_type == 'om_whatsapp' for channel in self):
                raise AccessError(_("A WhatsApp conversation stays one."))
        return super().write(vals)

    @api.depends('om_whatsapp_partner_id.image_128')
    def _compute_avatar_128(self):
        """ A conversation shows the photo of its contact, the one WhatsApp
        gave too: the picture of an unknown number is its own. """
        super()._compute_avatar_128()
        for channel in self.filtered(lambda c: c.channel_type == 'om_whatsapp' and not c.image_128):
            # sudo: the photo of the contact, which a user of the account may not read
            if photo := channel.om_whatsapp_partner_id.sudo().image_128:
                channel.avatar_128 = photo

    @api.model
    def _om_whatsapp_check_values(self, vals):
        if vals.get('channel_type') == 'om_whatsapp' or any(name.startswith('om_whatsapp_') for name in vals):
            raise AccessError(_("WhatsApp conversations are made and kept by their WhatsApp account."))

    def _om_whatsapp_sync_members(self):
        """ The users of the account and the contact are members. """
        for channel in self:
            partners = channel.om_whatsapp_account_id.user_ids.partner_id | channel.om_whatsapp_partner_id
            missing = partners - channel.channel_member_ids.partner_id
            if missing:
                channel._add_members(partners=missing, post_joined_message=False)

    def _om_whatsapp_set_document(self, document):
        """ The conversation shows the document it last spoke about. """
        if document and document._name not in ('discuss.channel', 'res.partner'):
            self.write({'om_whatsapp_res_model': document._name, 'om_whatsapp_res_id': document.id})

    def _om_whatsapp_get_document(self):
        self.ensure_one()
        if not self.om_whatsapp_res_model or self.om_whatsapp_res_model not in self.env:
            return None
        return self.env[self.om_whatsapp_res_model].browse(self.om_whatsapp_res_id).exists() or None

    def _om_whatsapp_address(self):
        """ Where a message of this conversation goes: the number, else the
        WhatsApp user ID of the customer. """
        self.ensure_one()
        return self.om_whatsapp_number or self.om_whatsapp_user_id or False

    def _om_whatsapp_label(self):
        """ How the customer of a conversation without a contact is shown: the
        number, else the username, else the WhatsApp user ID. """
        self.ensure_one()
        return self.om_whatsapp_number or (self.om_whatsapp_username and f'@{self.om_whatsapp_username}') \
            or self.om_whatsapp_user_id or False

    def _om_whatsapp_is_of(self, partner):
        """ Whether ``partner`` is the customer of this conversation, by
        their number or their WhatsApp user ID. """
        self.ensure_one()
        return bool((self.om_whatsapp_number and partner.phone_sanitized == self.om_whatsapp_number)
                    or (self.om_whatsapp_user_id and partner.om_whatsapp_user_id == self.om_whatsapp_user_id))

    def _om_whatsapp_link_partner(self, partner):
        """ The contact of an unknown number is made: the conversation is with
        them now, and so are its messages. """
        self.ensure_one()
        # the WhatsApp picture of the number becomes the photo of a contact that has none
        if self.image_128 and not partner.image_1920:
            partner.sudo().image_1920 = self.image_128
        self.write({'om_whatsapp_partner_id': partner.id, 'name': partner.name, 'image_128': False})
        if self.om_whatsapp_user_id and not partner.om_whatsapp_user_id:
            partner.sudo().write({'om_whatsapp_user_id': self.om_whatsapp_user_id,
                                  'om_whatsapp_username': self.om_whatsapp_username or False})
        self._om_whatsapp_sync_members()
        self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', self.id), ('message_type', '=', 'om_whatsapp'),
            ('author_id', '=', False),
        ]).write({'author_id': partner.id, 'email_from': False})
        self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_whatsapp'),
            *self.om_whatsapp_account_id._om_whatsapp_address_domain(self.om_whatsapp_number, self.om_whatsapp_user_id),
            ('res_partner_id', '=', False), ('mail_message_id.om_whatsapp_account_id', '=', self.om_whatsapp_account_id.id),
        ]).write({'res_partner_id': partner.id})

    def _om_whatsapp_merge_into(self, channel):
        """ The customer of this conversation, known by their WhatsApp user ID
        only, is the one of ``channel``, known by the number: its messages go
        there, and this one, empty, is archived (not deleted: the open pages
        may still be told about it in this transaction). """
        self.ensure_one()
        messages = self.env['mail.message'].sudo().search([('model', '=', 'discuss.channel'), ('res_id', '=', self.id)])
        messages.write({'res_id': channel.id})
        self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'discuss.channel'), ('res_id', '=', self.id), ('id', 'in', messages.attachment_ids.ids),
        ]).write({'res_id': channel.id})
        last = [date for date in (self.om_whatsapp_last_incoming, channel.om_whatsapp_last_incoming) if date]
        values = {'om_whatsapp_last_incoming': max(last, default=False)}
        if not channel.om_whatsapp_partner_id and self.om_whatsapp_partner_id:
            values['om_whatsapp_partner_id'] = self.om_whatsapp_partner_id.id
        user_id, username = self.om_whatsapp_user_id, self.om_whatsapp_username
        self.write({'active': False, 'om_whatsapp_user_id': False, 'om_whatsapp_res_model': False,
                    'om_whatsapp_res_id': False})
        # the user ID leaves this conversation before the other one takes it: one conversation each
        self.flush_recordset(['om_whatsapp_user_id'])
        channel.write(dict(values, om_whatsapp_user_id=user_id,
                           om_whatsapp_username=channel.om_whatsapp_username or username))

    def om_whatsapp_action_create_contact(self):
        """ The form of a new contact with the number of this conversation;
        saving it links them. """
        self.ensure_one()
        self.om_whatsapp_account_id._om_whatsapp_check_user()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Create Contact"),
            'res_model': 'res.partner',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_name': self.om_whatsapp_profile_name or self.om_whatsapp_username
                or self._om_whatsapp_address(),
                'default_phone': self.om_whatsapp_number,
                'default_om_whatsapp_user_id': self.om_whatsapp_user_id,
                'default_om_whatsapp_username': self.om_whatsapp_username,
                'om_whatsapp_channel_id': self.id,
            },
        }

    def om_whatsapp_action_open_document(self):
        self.ensure_one()
        document = self._om_whatsapp_get_document()
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
        """ What a user writes in a WhatsApp conversation goes out on WhatsApp. """
        if self.channel_type != 'om_whatsapp' or message_type != 'comment':
            return super().message_post(message_type=message_type, **kwargs)
        account = self.om_whatsapp_account_id
        account._om_whatsapp_check_user()
        account._om_whatsapp_check_free_text(self)
        message = super().message_post(message_type='om_whatsapp', om_whatsapp_account_id=account.id, **kwargs)
        notification = message._om_whatsapp_add_notification(
            self.om_whatsapp_number, self.om_whatsapp_partner_id, user_id=self.om_whatsapp_user_id)
        action = notification._om_whatsapp_send()
        if action:
            # posted from Discuss, which runs no action: the page of the user does
            self.env.user._bus_send('om_whatsapp/action', {'action': action})
        return message

    def _notify_get_recipients(self, message, **kwargs):
        """ The users of a conversation get the messages of the contact as
        web push, as in a chat. """
        if self.channel_type != 'om_whatsapp' or message.message_type != 'om_whatsapp':
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
        is_whatsapp = lambda channel: channel.channel_type == 'om_whatsapp'  # noqa: E731
        res.attr('om_whatsapp_number', predicate=is_whatsapp)
        res.attr('om_whatsapp_has_contact', lambda channel: bool(channel.om_whatsapp_partner_id), predicate=is_whatsapp)
        res.attr('om_whatsapp_provider', lambda channel: channel.om_whatsapp_account_id.provider, predicate=is_whatsapp)
        res.attr('om_whatsapp_free_text_until',
                 lambda channel: fields.Datetime.to_string(channel.om_whatsapp_account_id._om_whatsapp_free_text_until(channel)),
                 predicate=is_whatsapp)
        # sudo: the users of the conversation see the name of the document it speaks about
        res.attr(
            'om_whatsapp_document_name',
            lambda channel: (document := channel._om_whatsapp_get_document()) and document.sudo().display_name or False,
            predicate=is_whatsapp,
        )


class OmWhatsappAccount(models.Model):
    _inherit = 'om.whatsapp.account'

    def _om_whatsapp_get_channel(self, number, partner=False, profile_name=False, user_id=False, username=False):
        """ The conversation of this account with ``number``, or with the
        customer of the WhatsApp user ID ``user_id`` when WhatsApp does not
        share their number, made on the first message. A conversation known
        by one of them learns the other; two conversations of the same
        customer become one. Without a contact, it is named by the number (or
        the username, or the user ID), and the name the person gave
        themselves in WhatsApp. """
        self.ensure_one()
        number = self._om_whatsapp_clean_number(number) or False
        Channel = self.env['discuss.channel'].sudo()
        domain = [('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', '=', self.id)]
        by_number = Channel.search([*domain, ('om_whatsapp_number', '=', number)], limit=1) if number else Channel
        by_user_id = Channel.search([*domain, ('om_whatsapp_user_id', '=', user_id)], limit=1) if user_id else Channel
        if by_number and by_user_id and by_number != by_user_id:
            if by_user_id.om_whatsapp_number:
                # the user ID moved to another number: the conversation of the number takes it
                by_user_id.write({'om_whatsapp_user_id': False})
                by_user_id.flush_recordset(['om_whatsapp_user_id'])
            else:
                by_user_id._om_whatsapp_merge_into(by_number)
        channel = by_number or by_user_id
        learned = {}
        if channel and number and not channel.om_whatsapp_number:
            learned['om_whatsapp_number'] = number
        if channel and user_id and channel.om_whatsapp_user_id != user_id:
            learned['om_whatsapp_user_id'] = user_id
        if channel and username and channel.om_whatsapp_username != username:
            learned['om_whatsapp_username'] = username
        if learned:
            channel.write(learned)
        profile_name = profile_name or channel.om_whatsapp_profile_name
        label = channel._om_whatsapp_label() if channel else number or (f'@{username}' if username else user_id)
        name = partner.name if partner else (f'{profile_name} ({label})' if profile_name else label)
        if not channel:
            channel = Channel.create({
                'name': name,
                'channel_type': 'om_whatsapp',
                'om_whatsapp_account_id': self.id,
                'om_whatsapp_number': number,
                'om_whatsapp_user_id': user_id or False,
                'om_whatsapp_username': username or False,
                'om_whatsapp_partner_id': partner.id if partner else False,
                'om_whatsapp_profile_name': profile_name or False,
                'channel_partner_ids': [Command.link(p.id) for p in self.user_ids.partner_id | (partner or self.env['res.partner'])],
            })
            # Discuss adds whoever makes a channel: only the users of the account belong here
            channel.channel_member_ids.filtered(
                lambda m: m.partner_id not in self.user_ids.partner_id | (partner or self.env['res.partner'])).unlink()
        elif partner and channel.om_whatsapp_partner_id != partner:
            channel._om_whatsapp_link_partner(partner)
        elif not partner and profile_name and profile_name != channel.om_whatsapp_profile_name:
            # a conversation with a contact keeps the name of the contact
            channel.write({'om_whatsapp_profile_name': profile_name,
                           **({} if channel.om_whatsapp_partner_id else {'name': name})})
        elif not partner and not channel.om_whatsapp_partner_id and learned and name != channel.name:
            # named by the number now, or by the new username
            channel.name = name
        channel._om_whatsapp_sync_members()
        return channel
