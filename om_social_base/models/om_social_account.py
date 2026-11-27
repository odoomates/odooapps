import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import plaintext2html

from odoo.addons.mail.tools.discuss import Store

_logger = logging.getLogger(__name__)

# the profile picture of a customer without a contact is fetched again after this long
PICTURE_REFRESH = timedelta(days=7)
# only for the conversations that spoke this recently
PICTURE_ACTIVE = timedelta(days=30)


class OmSocialAccount(models.Model):
    """ An account of a messaging channel (a WhatsApp number...) Odoo sends
    from and receives on. The provider decides how a message leaves Odoo:
    provider modules add their key to ``provider`` and implement
    ``_om_social_send_<provider>``; channel modules add their channel to
    ``channel``. """
    _name = 'om.social.account'
    _description = 'Social Account'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    channel = fields.Selection([('whatsapp', 'WhatsApp')], required=True, default='whatsapp')
    provider = fields.Selection([], required=True)
    address = fields.Char(
        'Address', help="The number or the handle this account sends from, shown to the users.")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    user_ids = fields.Many2many(
        'res.users', string='Allowed Users', default=lambda self: self.env.user,
        domain="[('share', '=', False)]",
        help="Users who answer from this account.")
    reply_days = fields.Integer(
        'Reply Window (days)', default=7,
        help="A reply that quotes no message goes to the document of the last message sent to that customer "
             "within these days; later, or without one, it goes to the conversation only.")
    fetch_pictures = fields.Boolean(
        'Profile Pictures', default=True,
        help="Show the profile picture of a customer who has no photo in Odoo: it becomes the photo of the contact, "
             "or of the conversation of an unknown customer. A photo set in Odoo is never replaced. With the "
             "providers that can, as the privacy settings of the customer allow.")
    receive_unknown = fields.Boolean(
        'Keep Chats of Unknown Customers', default=True,
        help="The messages of a customer Odoo does not know, neither a contact nor a chat about a document, open a "
             "conversation where a contact can be made. Unchecked, they are not kept: an account also used for "
             "private chats keeps them out of Odoo. Groups and status are never kept.")
    can_send_files = fields.Boolean(compute='_compute_capabilities')
    can_send_batch = fields.Boolean(compute='_compute_capabilities')
    can_send_unattended = fields.Boolean(compute='_compute_capabilities')
    can_send_user_ref = fields.Boolean('Sends to User IDs', compute='_compute_can_send_user_ref')
    message_count = fields.Integer(compute='_compute_message_count')

    @api.depends('provider')
    def _compute_capabilities(self):
        """ Provider modules extend this when their provider sends files,
        several messages at once, or without a user at the screen (from the
        server: automation rules, scheduled actions). """
        for account in self:
            account.can_send_files = False
            account.can_send_batch = False
            account.can_send_unattended = False

    @api.depends('provider')
    def _compute_can_send_user_ref(self):
        """ Provider modules extend this when their provider sends to the user
        ID the channel gives a customer whose address is unknown. """
        self.can_send_user_ref = False

    def _compute_message_count(self):
        counts = dict(self.env['mail.message']._read_group(
            [('message_type', '=', 'om_social'), ('om_social_account_id', 'in', self.ids)],
            ['om_social_account_id'], ['__count']))
        for account in self:
            account.message_count = counts.get(account, 0)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_conversations(self):
        """ The conversations of an account go with it: archive it instead. """
        counts = dict(self.env['discuss.channel'].sudo()._read_group(
            [('channel_type', '=', 'om_social'), ('om_social_account_id', 'in', self.ids)],
            ['om_social_account_id'], ['__count']))
        for account in self:
            if counts.get(account):
                raise UserError(_("%(account)s has %(count)s conversation(s), which would be deleted with it: "
                                  "archive it instead.", account=account.name, count=counts[account]))

    @api.model
    def _get_default_account(self, channel=False):
        domain = [('user_ids', 'in', self.env.user.id), ('company_id', 'in', self.env.companies.ids)]
        if channel:
            domain.append(('channel', '=', channel))
        return self.search(domain, limit=1)

    def _om_social_channel_label(self):
        self.ensure_one()
        return dict(self._fields['channel']._description_selection(self.env)).get(self.channel) or _("Social")

    def action_view_messages(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_social_base.om_social_message_action')
        action['domain'] = [('message_type', '=', 'om_social'), ('om_social_account_id', '=', self.id)]
        return action

    def _om_social_check_user(self):
        self.ensure_one()
        if self.env.user not in self.user_ids:
            raise UserError(_("You are not allowed to use the account %(account)s.", account=self.display_name))

    # ------------------------------------------------------------
    # ADDRESSES: how a channel writes the number or handle of a customer
    # ------------------------------------------------------------

    def _om_social_format_address(self, address):
        """ An address a provider gives, as conversations and messages keep
        it. Channel modules extend this (a phone number in its international
        format...). """
        self.ensure_one()
        return self._om_social_clean_address(address)

    @api.model
    def _om_social_clean_address(self, address):
        return address.strip() if address else address

    @api.model
    def _om_social_is_user_ref(self, address):
        """ Whether ``address`` is a user ID the channel gives a customer,
        rather than an address. """
        return False

    @api.model
    def _om_social_address_domain(self, address, user_ref=False):
        """ The notifications of the chat with ``address``, or with the user
        ID ``user_ref``. """
        return [('om_social_address', 'in', [value for value in (address, user_ref) if value] or [False])]

    # ------------------------------------------------------------
    # PROVIDER CONTRACT: SENDING
    # ------------------------------------------------------------

    def _om_social_send(self, notifications):
        """ Hand ``notifications`` (mail.notification of this account, ready)
        to the provider. The provider moves them with
        ``_om_social_set_status``, now or later, and may return an action for
        the browser to run. """
        self.ensure_one()
        if not self.can_send_batch and len(notifications) > 1:
            raise UserError(_("%(account)s sends one message at a time.", account=self.display_name))
        send = getattr(self, f'_om_social_send_{self.provider}', None)
        if not send:
            raise UserError(_("The provider of %(account)s cannot send messages.", account=self.display_name))
        if not self.can_send_user_ref:
            unreachable = notifications.filtered(
                lambda n: not n.om_social_address or self._om_social_is_user_ref(n.om_social_address))
            if unreachable:
                unreachable._om_social_set_status('failed', _(
                    "%(account)s sends to addresses only: the contact has a user ID and no address.",
                    account=self.display_name))
                notifications -= unreachable
                if not notifications:
                    return None
        return send(notifications)

    def _om_social_send_automated(self, notifications):
        """ Send messages no user sent by hand: an automation rule, a scheduled
        action. A provider that sends from the server sends them; the others
        fail them with the reason, to be sent again from the chatter. """
        self.ensure_one()
        if self.can_send_unattended:
            if self.can_send_batch:
                return self._om_social_send(notifications)
            for notification in notifications:
                self._om_social_send(notification)
            return None
        notifications._om_social_set_status('failed', _(
            "%(account)s cannot send by itself: send it again from the chatter.", account=self.display_name))
        return None

    def _om_social_free_text_until(self, channel):
        """ Until when the provider accepts free text in this conversation:
        False when always. """
        return False

    def _om_social_check_free_text(self, channel):
        """ Refuse free text the provider would refuse. """
        until = self._om_social_free_text_until(channel)
        if until and until < fields.Datetime.now():
            raise UserError(_(
                "%(contact)s has not written in the last 24 hours: only an approved template can go now. Send one "
                "from the contact or the document, and the conversation opens again when they answer.",
                contact=channel.name))

    def _om_social_user_at_screen(self):
        """ Whether the current user triggered this from their browser, and
        sends from this account: a browser provider can then send. """
        self.ensure_one()
        return bool(request and request.session.uid == self.env.uid and self.env.user in self.user_ids)

    def _om_social_send_action(self, action):
        """ Run ``action`` in the browser of the user (Discuss runs no action
        itself): one tab of the browser runs it. """
        if action:
            self.env.user._bus_send('om_social/action', {'action': action})

    def _om_social_send_reaction(self, message, emoji):
        """ React with ``emoji`` (empty: take the reaction back) to
        ``message``, a message of this account with its id in the channel.
        The provider implements ``_om_social_react_<provider>(address,
        message, emoji, from_me)`` and may return an action for the browser of
        the user; a provider without it does not send reactions. A reaction
        that cannot go never stops the one made in Odoo: the user is told
        why. """
        self.ensure_one()
        react = getattr(self, f'_om_social_react_{self.provider}', None)
        address, from_me = message._om_social_chat()
        if not react or not address:
            return
        try:
            with self.env.cr.savepoint():
                action = react(address, message.sudo(), emoji, from_me)
        except Exception as error:  # noqa: BLE001
            expected = isinstance(error, UserError)
            _logger.warning("Reaction to %s not sent: %s", message, error, exc_info=not expected)
            reason = error.args[0] if expected else _("an unexpected error, see the server log.")
            self.env.user._bus_send('simple_notification', {
                'type': 'danger',
                'message': _("The reaction was not sent to %(channel)s: %(reason)s",
                             channel=self._om_social_channel_label(), reason=reason),
            })
            return
        self._om_social_send_action(action)

    def _om_social_send_receipt(self, address, message_ids, kind):
        """ Tell the channel the messages ``message_ids`` of the chat of
        ``address`` were read (``kind`` 'read') or played ('played'). The
        provider implements ``_om_social_receipt_<provider>(address, ids,
        kind)``, which returns an action for the browser of the user, or None;
        a provider without it sends no receipts. Never raises: a receipt is not
        worth an error.

        :return: whether the receipt went, or was handed to the browser
        """
        self.ensure_one()
        receipt = getattr(self, f'_om_social_receipt_{self.provider}', None)
        if not receipt:
            return False
        try:
            with self.env.cr.savepoint():
                action = receipt(address, message_ids, kind)
        except Exception as error:  # noqa: BLE001
            _logger.info("%s receipt of %s not sent: %s", kind, message_ids, error)
            return False
        self._om_social_send_action(action)
        return True

    # ------------------------------------------------------------
    # PROFILE PICTURES: only for the customers without a photo in Odoo
    # ------------------------------------------------------------

    def _om_social_pictures_due(self, limit=3):
        """ The recent conversations of this account whose customer has no
        photo in Odoo, and whose picture was not looked for lately. """
        self.ensure_one()
        Channel = self.env['discuss.channel'].sudo()
        if not self.fetch_pictures:
            return Channel
        now = fields.Datetime.now()
        channels = Channel.search([
            ('channel_type', '=', 'om_social'), ('om_social_account_id', '=', self.id),
            ('om_social_last_incoming', '>=', now - PICTURE_ACTIVE),
            '|', ('om_social_picture_date', '=', False), ('om_social_picture_date', '<', now - PICTURE_REFRESH),
        ], order='om_social_last_incoming desc', limit=limit * 10)
        return channels.filtered(lambda c: not c.om_social_partner_id.image_1920 and c.om_social_address)[:limit]

    def _om_social_set_picture(self, address, data):
        """ The profile picture of ``address`` (base64, or False when the
        customer shows none): the photo of their contact when it has none,
        else of the conversation of an unknown customer. """
        self.ensure_one()
        channel = self.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'om_social'), ('om_social_account_id', '=', self.id),
            ('om_social_address', '=', address),
        ], limit=1)
        if not channel:
            return False
        channel.om_social_picture_date = fields.Datetime.now()
        if not data or not self.fetch_pictures:
            return False
        partner = channel.om_social_partner_id.sudo()
        try:
            with self.env.cr.savepoint():
                if not partner:
                    channel.image_128 = data
                elif not partner.image_1920:
                    partner.image_1920 = data
                    # the conversation shows it: its open pages get the new avatar
                    Store(bus_channel=channel).add(channel, ['avatar_cache_key'])
        except Exception as error:  # noqa: BLE001
            _logger.info("Profile picture of %s not kept: %s", address, error)
            return False
        return True

    @api.model
    def _cron_om_social_pictures(self, limit=20):
        """ The providers that read the pictures from the server
        (``_om_social_picture_<provider>(address)``: base64 or False). """
        for account in self.search([('fetch_pictures', '=', True)]):
            fetch = getattr(account, f'_om_social_picture_{account.provider}', None)
            if not fetch:
                continue
            for channel in account._om_social_pictures_due(limit=limit):
                try:
                    data = fetch(channel.om_social_address)
                except Exception as error:  # noqa: BLE001
                    _logger.info("Profile picture of %s not read: %s", channel.om_social_address, error)
                    data = False
                account._om_social_set_picture(channel.om_social_address, data)

    # ------------------------------------------------------------
    # PROVIDER CONTRACT: RECEIVING
    # ------------------------------------------------------------

    def _om_social_find_partner(self, address, user_ref=False):
        """ The contact of ``address``, or of the user ID ``user_ref`` (its
        identity in the channel). """
        self.ensure_one()
        if user_ref:
            partner = self.env['om.social.identity']._om_social_search(self.channel, user_ref=user_ref).filtered(
                lambda i: i.partner_id and i.partner_id.company_id in (self.company_id, self.env['res.company'])
            )[:1].partner_id
            if partner or not address:
                return partner
        if not address:
            return self.env['res.partner']
        return self._om_social_find_partner_by_address(address)

    def _om_social_find_partner_by_address(self, address):
        """ The contact of ``address``: by default the one of its identity.
        Channel modules extend this (by the phone of the contact...). """
        self.ensure_one()
        return self.env['om.social.identity']._om_social_search(self.channel, address=address).filtered(
            lambda i: i.partner_id and i.partner_id.company_id in (self.company_id, self.env['res.company'])
        )[:1].partner_id

    def _om_social_find_document(self, address, quoted_id=False, user_ref=False):
        """ The document a message of ``address`` (or of the user ID
        ``user_ref``) belongs to: the one of the message it quotes, else the
        one of the last message sent to them within the reply window. """
        self.ensure_one()
        message = self.env['mail.message']
        if quoted_id:
            message = message.sudo().search([
                ('om_social_account_id', '=', self.id), ('om_social_message_id', '=', quoted_id),
                ('model', 'not in', [False, 'discuss.channel']),
            ], limit=1)
        if not message and self.reply_days > 0:
            message = self.env['mail.notification'].sudo().search([
                ('notification_type', '=', 'om_social'),
                *self._om_social_address_domain(*self._om_social_chat_addresses(address, user_ref)),
                ('notification_status', 'in', ('pending', 'sent')),
                ('mail_message_id.om_social_account_id', '=', self.id),
                ('mail_message_id.model', 'not in', [False, 'discuss.channel']),
                ('mail_message_id.date', '>=', fields.Datetime.now() - timedelta(days=self.reply_days)),
            ], order='id desc', limit=1).mail_message_id
        if not message or message.model not in self.env:
            return None
        document = self.env[message.model].sudo().browse(message.res_id).exists()
        return document if document and hasattr(document, 'message_post') else None

    def _om_social_chat_addresses(self, address, user_ref=False):
        """ (address, user ID) of a chat, the one missing learned from its
        conversation: a message to a customer by their address is found by
        their user ID too, and the other way. """
        self.ensure_one()
        if address and user_ref:
            return address, user_ref
        Channel = self.env['discuss.channel'].sudo()
        domain = [('channel_type', '=', 'om_social'), ('om_social_account_id', '=', self.id)]
        if user_ref:
            channel = Channel.search([*domain, ('om_social_identity_id.user_ref', '=', user_ref)], limit=1)
            return channel.om_social_address or False, user_ref
        if address:
            channel = Channel.search([*domain, ('om_social_address', '=', address)], limit=1)
            return address, channel.om_social_identity_id.user_ref or False
        return False, False

    def _om_social_find_sent(self, address, body, message_id, user_ref=False):
        """ A message of the phone may be one Odoo just sent, before the
        provider gave its id: give it the id instead of logging it twice. """
        self.ensure_one()
        notifications = self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_social'),
            *self._om_social_address_domain(*self._om_social_chat_addresses(address, user_ref)),
            # process: a browser is sending it, and has not told its id yet
            ('notification_status', 'in', ('ready', 'process', 'pending', 'sent')),
            ('mail_message_id.om_social_account_id', '=', self.id),
            ('mail_message_id.om_social_message_id', '=', False),
            ('mail_message_id.date', '>=', fields.Datetime.now() - timedelta(minutes=10)),
        ], order='id desc')
        sent = notifications.filtered(lambda n: n.mail_message_id._om_social_text() == (body or '').strip())[:1]
        if not sent:
            return None
        sent.mail_message_id.om_social_message_id = message_id or False
        sent._om_social_set_status('sent')
        return sent.mail_message_id

    def _om_social_accepts(self, address, quoted_id=False, user_ref=False):
        """ Whether a message of ``address`` (or of the user ID ``user_ref``)
        is kept: a contact, a chat about a document, or anyone when the
        account keeps the unknown ones. """
        self.ensure_one()
        return bool(self.receive_unknown or self._om_social_find_partner(address, user_ref=user_ref)
                    or self._om_social_find_document(address, quoted_id, user_ref=user_ref))

    def _om_social_receive(self, address, body='', message_id=False, attachments=None, quoted_id=False, from_me=False,
                           profile_name=False, voice=False, user_ref=False, username=False):
        """ Record a message of a chat of this account: received from
        ``address``, or sent to it from the phone itself when ``from_me``. It
        goes to the conversation with that address, as an answer to the
        message it quotes, and to the document it answers. A customer Odoo
        does not know is skipped, unless the account keeps them.
        ``attachments`` is a list of (filename, content); ``voice`` makes them
        a voice message. ``profile_name`` is the name the contact gave
        themselves in the channel. A message seen twice is kept once.
        ``user_ref`` is the user ID the channel gives the customer and
        ``username`` their username, when the provider gives them; ``address``
        may then be empty, when the channel does not share it.

        :return: the mail.message of the conversation, or False when skipped
        """
        self.ensure_one()
        Message = self.env['mail.message'].sudo()
        if message_id:
            existing = Message.search([('om_social_account_id', '=', self.id),
                                       ('om_social_message_id', '=', message_id)], limit=1)
            if existing:
                return existing
        address = self._om_social_format_address(address) if address else False
        if not address and not user_ref:
            return False
        if from_me and (sent := self._om_social_find_sent(address, body, message_id, user_ref=user_ref)):
            return sent
        partner = self._om_social_find_partner(address, user_ref=user_ref)
        document = self._om_social_find_document(address, quoted_id, user_ref=user_ref)
        if not document and not partner and not self.receive_unknown:
            return False
        channel = self._om_social_get_channel(address, partner, profile_name=profile_name, user_ref=user_ref,
                                              username=username)
        channel._om_social_set_document(document)
        message = False
        for target in (document, channel):
            if not target:
                continue
            post_values = {'attachments': attachments or [], 'om_social_message_id': message_id or False}
            if target == channel and quoted_id:
                # shown in the conversation as an answer to the message it quotes
                post_values['parent_id'] = Message.search([
                    ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
                    ('om_social_message_id', '=', quoted_id),
                ], limit=1).id or False
            if from_me:
                posted = target._message_om_social(self, body, address or user_ref, partner=partner,
                                                   status='pending', **post_values)
            else:
                posted = target.message_post(
                    body=plaintext2html(body) if body else '',
                    message_type='om_social',
                    subtype_xmlid='mail.mt_comment',
                    author_id=partner.id,
                    email_from=None if partner else channel.name,
                    om_social_account_id=self.id,
                    **post_values,
                )
            if voice:
                posted.attachment_ids._set_voice_metadata()
            message = posted
        if not from_me:
            channel.om_social_last_incoming = fields.Datetime.now()
        return message

    def _om_social_receive_reaction(self, address, message_id, emoji, from_me=False, user_ref=False):
        """ A reaction of the contact (or of the user, from the phone) to a
        message: shown on it in Odoo, on the document and in the conversation.
        One reaction per person; no emoji takes it back. """
        self.ensure_one()
        messages = self.env['mail.message'].sudo().search(
            [('om_social_account_id', '=', self.id), ('om_social_message_id', '=', message_id)])
        if not messages:
            return False
        if from_me:
            partner = self.env.user.partner_id
        else:
            address = self._om_social_format_address(address) if address else False
            partner = self._om_social_find_partner(address, user_ref=user_ref)
        if not partner:
            return False
        Reaction = self.env['mail.message.reaction'].sudo()
        for message in messages:
            previous = Reaction.search([('message_id', '=', message.id), ('partner_id', '=', partner.id)])
            if emoji and previous.content == emoji:
                continue
            contents = set(previous.mapped('content'))
            previous.unlink()
            if emoji:
                Reaction.create({'message_id': message.id, 'partner_id': partner.id, 'content': emoji})
                contents.add(emoji)
            for content in contents:
                message._bus_send_reaction_group(content)
        return True

    def _om_social_update_status(self, message_id, status, failure_reason=False):
        """ Status update of a sent message, by its id in the channel: on the
        document and in the conversation. """
        self.ensure_one()
        messages = self.env['mail.message'].sudo().search(
            [('om_social_account_id', '=', self.id), ('om_social_message_id', '=', message_id)])
        return messages._om_social_notifications()._om_social_set_status(status, failure_reason)
