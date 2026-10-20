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

    def init(self):
        super().init()
        # one conversation an account and number
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS discuss_channel__om_whatsapp_number_unique
            ON discuss_channel (om_whatsapp_account_id, om_whatsapp_number) WHERE channel_type = 'om_whatsapp'
        """)

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

    @api.depends('om_whatsapp_partner_id.avatar_128')
    def _compute_avatar_128(self):
        """ A conversation shows the photo of its contact, the one WhatsApp
        gave too: the picture of an unknown number is its own. """
        super()._compute_avatar_128()
        for channel in self.filtered(lambda c: c.channel_type == 'om_whatsapp' and not c.image_128):
            # sudo: the photo of the contact, which a user of the account may not read, else its initial
            if photo := channel.om_whatsapp_partner_id.sudo().avatar_128:
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

    def _om_whatsapp_link_partner(self, partner):
        """ The contact of an unknown number is made: the conversation is with
        them now, and so are its messages. """
        self.ensure_one()
        # the WhatsApp picture of the number becomes the photo of a contact that has none
        if self.image_128 and not partner.image_1920:
            partner.sudo().image_1920 = self.image_128
        self.write({'om_whatsapp_partner_id': partner.id, 'name': partner.name, 'image_128': False})
        self._om_whatsapp_sync_members()
        self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', self.id), ('message_type', '=', 'om_whatsapp'),
            ('author_id', '=', False),
        ]).write({'author_id': partner.id, 'email_from': False})
        self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_whatsapp'), ('om_whatsapp_number', '=', self.om_whatsapp_number),
            ('res_partner_id', '=', False), ('mail_message_id.om_whatsapp_account_id', '=', self.om_whatsapp_account_id.id),
        ]).write({'res_partner_id': partner.id})

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
                'default_name': self.om_whatsapp_profile_name or self.om_whatsapp_number,
                'default_phone': self.om_whatsapp_number,
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
        notification = message._om_whatsapp_add_notification(self.om_whatsapp_number, self.om_whatsapp_partner_id)
        action = notification._om_whatsapp_send()
        if action:
            # posted from Discuss, which runs no action: the page of the user does
            self.env.user._bus_send('om_whatsapp/action', {'action': action})
        return message

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        """ The users of a conversation get the messages of the contact as
        web push, as in a chat. """
        if self.channel_type != 'om_whatsapp' or message.message_type != 'om_whatsapp':
            return super()._notify_get_recipients(message, msg_vals, **kwargs)
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

    def _channel_basic_info(self):
        """ What Discuss knows of a conversation; a change of it reaches the
        open pages, as for the fields of every channel. """
        data = super()._channel_basic_info()
        if self.channel_type != 'om_whatsapp':
            return data
        # sudo: the members of the conversation see how its account sends, and the name of its document
        account = self.om_whatsapp_account_id.sudo()
        document = self._om_whatsapp_get_document()
        data.update({
            'om_whatsapp_number': self.om_whatsapp_number,
            'om_whatsapp_has_contact': bool(self.om_whatsapp_partner_id),
            'om_whatsapp_provider': account.provider,
            'om_whatsapp_free_text_until': fields.Datetime.to_string(account._om_whatsapp_free_text_until(self)),
            'om_whatsapp_document_name': document and document.sudo().display_name or False,
        })
        return data


class OmWhatsappAccount(models.Model):
    _inherit = 'om.whatsapp.account'

    def _om_whatsapp_get_channel(self, number, partner=False, profile_name=False):
        """ The conversation of this account with ``number``, made on the first
        message. Without a contact, it is named by the number, and the name
        the person gave themselves in WhatsApp. """
        self.ensure_one()
        Channel = self.env['discuss.channel'].sudo()
        channel = Channel.search([
            ('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', '=', self.id), ('om_whatsapp_number', '=', number),
        ], limit=1)
        profile_name = profile_name or channel.om_whatsapp_profile_name
        name = partner.name if partner else (f'{profile_name} ({number})' if profile_name else number)
        if not channel:
            channel = Channel.create({
                'name': name,
                'channel_type': 'om_whatsapp',
                'om_whatsapp_account_id': self.id,
                'om_whatsapp_number': number,
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
            channel.write({'om_whatsapp_profile_name': profile_name, 'name': name})
        channel._om_whatsapp_sync_members()
        return channel
