import base64
import logging
from datetime import timedelta
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.translate import LazyTranslate

from odoo.addons.mail.tools.discuss import Store

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)

# the WhatsApp picture of a number without a contact is fetched again after this long
PICTURE_REFRESH = timedelta(days=7)
# only for the conversations that spoke this recently
PICTURE_ACTIVE = timedelta(days=30)

# what a status or an ack of WhatsApp means for a message sent
ITEM_STATUS = {'sent': 'sent', 'delivered': 'delivered', 'read': 'read', 'failed': 'failed', 2: 'delivered', 3: 'read', 4: 'read'}
# kinds of messages with a file, named when the file could not be read
MEDIA_LABELS = {
    'image': _lt("Picture"),
    'document': _lt("Document"),
    'sticker': _lt("Sticker"),
    'ptt': _lt("Voice message"),
    'audio': _lt("Audio"),
    'video': _lt("Video"),
}
from odoo.tools import plaintext2html


class OmWhatsappAccount(models.Model):
    """ A WhatsApp number Odoo sends from. The provider decides how a message
    leaves Odoo: provider modules add their key to ``provider`` and implement
    ``_om_whatsapp_send_<provider>``; the base ships Click to Chat, which opens
    the chat in a new tab with the text filled in. """
    _name = 'om.whatsapp.account'
    _description = 'WhatsApp Account'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    provider = fields.Selection([('link', 'Click to Chat')], required=True, default='link')
    phone = fields.Char('WhatsApp Number', help="The number this account sends from, shown to the users.")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    user_ids = fields.Many2many(
        'res.users', string='Allowed Users', default=lambda self: self.env.user,
        domain="[('share', '=', False)]",
        help="Users who can send from this account.")
    reply_days = fields.Integer(
        'Reply Window (days)', default=7,
        help="A reply that quotes no message goes to the document of the last message sent to that number "
             "within these days; later, or without one, it goes to the conversation only.")
    fetch_pictures = fields.Boolean(
        'Profile Pictures', default=True,
        help="Show the WhatsApp profile picture of a customer who has no photo in Odoo: it becomes the photo of "
             "the contact, or of the conversation of an unknown number. A photo set in Odoo is never replaced. "
             "With the providers that can (WhatsApp Web, WhatsApp QR), as the privacy settings of the customer "
             "allow.")
    receive_unknown = fields.Boolean(
        'Keep Chats of Unknown Numbers', default=True,
        help="The messages of a number Odoo does not know, neither a contact nor a chat about a document, open a "
             "conversation where a contact can be made. Unchecked, they are not kept: a WhatsApp also used for "
             "private chats keeps them out of Odoo. Groups and status are never kept.")
    can_send_files = fields.Boolean(compute='_compute_capabilities')
    can_send_batch = fields.Boolean(compute='_compute_capabilities')
    can_send_unattended = fields.Boolean(compute='_compute_capabilities')
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

    def _compute_message_count(self):
        counts = dict(self.env['mail.message']._read_group(
            [('message_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', 'in', self.ids)],
            ['om_whatsapp_account_id'], ['__count']))
        for account in self:
            account.message_count = counts.get(account, 0)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_conversations(self):
        """ The conversations of an account go with it: archive it instead. """
        counts = dict(self.env['discuss.channel'].sudo()._read_group(
            [('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', 'in', self.ids)],
            ['om_whatsapp_account_id'], ['__count']))
        for account in self:
            if counts.get(account):
                raise UserError(_("%(account)s has %(count)s WhatsApp conversation(s), which would be deleted with it: "
                                  "archive it instead.", account=account.name, count=counts[account]))

    @api.model
    def _get_default_account(self):
        return self.search([('user_ids', 'in', self.env.user.id), ('company_id', 'in', self.env.companies.ids)], limit=1)

    def action_view_messages(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_whatsapp_base.om_whatsapp_message_action')
        action['domain'] = [('message_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', '=', self.id)]
        return action

    def _om_whatsapp_check_user(self):
        self.ensure_one()
        if self.env.user not in self.user_ids:
            raise UserError(_("You are not allowed to use the WhatsApp account %(account)s.", account=self.display_name))

    # ------------------------------------------------------------
    # PROVIDER CONTRACT: SENDING
    # ------------------------------------------------------------

    def _om_whatsapp_send(self, notifications):
        """ Hand ``notifications`` (mail.notification of this account, ready)
        to the provider. The provider moves them with
        ``_om_whatsapp_set_status``, now or later, and may return an action for
        the browser to run. """
        self.ensure_one()
        if not self.can_send_batch and len(notifications) > 1:
            raise UserError(_("%(account)s sends one message at a time.", account=self.display_name))
        send = getattr(self, f'_om_whatsapp_send_{self.provider}', None)
        if not send:
            raise UserError(_("The provider of %(account)s cannot send messages.", account=self.display_name))
        return send(notifications)

    def _om_whatsapp_send_automated(self, notifications):
        """ Send messages no user sent by hand: an automation rule, a scheduled
        action. A provider that sends from the server sends them; the others
        fail them with the reason, to be sent again from the chatter. """
        self.ensure_one()
        if self.can_send_unattended:
            if self.can_send_batch:
                return self._om_whatsapp_send(notifications)
            for notification in notifications:
                self._om_whatsapp_send(notification)
            return None
        notifications._om_whatsapp_set_status('failed', _(
            "%(account)s cannot send by itself: send it again from the chatter.", account=self.display_name))
        return None

    def _om_whatsapp_free_text_until(self, channel):
        """ Until when the provider accepts free text in this conversation:
        False when always. """
        return False

    def _om_whatsapp_check_free_text(self, channel):
        """ Refuse free text the provider would refuse. """
        until = self._om_whatsapp_free_text_until(channel)
        if until and until < fields.Datetime.now():
            raise UserError(_(
                "%(contact)s has not written in the last 24 hours: WhatsApp accepts only an approved template now. "
                "Send one from the contact or the document, and the conversation opens again when they answer.",
                contact=channel.name))

    def _om_whatsapp_user_at_screen(self):
        """ Whether the current user triggered this from their browser, and
        sends from this account: a browser provider can then send. """
        self.ensure_one()
        return bool(request and request.session.uid == self.env.uid and self.env.user in self.user_ids)

    def _om_whatsapp_send_link(self, notifications):
        """ Click to Chat cannot tell whether the user pressed send, so the
        message counts as sent once the chat is open. """
        notifications._om_whatsapp_set_status('sent')
        digits = ''.join(char for char in notifications.om_whatsapp_number if char.isdigit())
        return {
            'type': 'ir.actions.act_url',
            'url': f'https://wa.me/{digits}?text={quote(notifications.mail_message_id._om_whatsapp_text())}',
            'target': 'new',
            'close': True,
        }

    def _om_whatsapp_send_reaction(self, message, emoji):
        """ React with ``emoji`` (empty: take the reaction back) in WhatsApp to
        ``message``, a message of this account with its WhatsApp id. The
        provider implements ``_om_whatsapp_react_<provider>(number, message,
        emoji, from_me)`` and may return an action for the browser of the
        user; a provider without it does not send reactions (Click to Chat).
        A reaction that cannot go never stops the one made in Odoo: the user
        is told why. """
        self.ensure_one()
        react = getattr(self, f'_om_whatsapp_react_{self.provider}', None)
        number, from_me = message._om_whatsapp_chat()
        if not react or not number:
            return
        try:
            with self.env.cr.savepoint():
                action = react(number, message.sudo(), emoji, from_me)
        except Exception as error:  # noqa: BLE001
            expected = isinstance(error, UserError)
            _logger.warning("WhatsApp reaction to %s not sent: %s", message, error, exc_info=not expected)
            reason = error.args[0] if expected else _("an unexpected error, see the server log.")
            self.env.user._bus_send('simple_notification', {
                'type': 'danger',
                'message': _("The reaction was not sent to WhatsApp: %(reason)s", reason=reason),
            })
            return
        if action:
            self.env.user._bus_send('om_whatsapp/action', {'action': action})

    def _om_whatsapp_send_receipt(self, number, whatsapp_ids, kind):
        """ Tell WhatsApp the messages ``whatsapp_ids`` of the chat of
        ``number`` were read (``kind`` 'read') or played ('played'). The
        provider implements ``_om_whatsapp_receipt_<provider>(number, ids,
        kind)``, which returns an action for the browser of the user, or None;
        a provider without it sends no receipts. Never raises: a receipt is not
        worth an error.

        :return: whether the receipt went, or was handed to the browser
        """
        self.ensure_one()
        receipt = getattr(self, f'_om_whatsapp_receipt_{self.provider}', None)
        if not receipt:
            return False
        try:
            with self.env.cr.savepoint():
                action = receipt(number, whatsapp_ids, kind)
        except Exception as error:  # noqa: BLE001
            _logger.info("WhatsApp %s receipt of %s not sent: %s", kind, whatsapp_ids, error)
            return False
        if action:
            self.env.user._bus_send('om_whatsapp/action', {'action': action})
        return True

    # ------------------------------------------------------------
    # PROFILE PICTURES: only for the customers without a photo in Odoo
    # ------------------------------------------------------------

    def _om_whatsapp_pictures_due(self, limit=3):
        """ The recent conversations of this account whose customer has no
        photo in Odoo, and whose picture was not looked for lately. """
        self.ensure_one()
        Channel = self.env['discuss.channel'].sudo()
        if not self.fetch_pictures:
            return Channel
        now = fields.Datetime.now()
        channels = Channel.search([
            ('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', '=', self.id),
            ('om_whatsapp_last_incoming', '>=', now - PICTURE_ACTIVE),
            '|', ('om_whatsapp_picture_date', '=', False), ('om_whatsapp_picture_date', '<', now - PICTURE_REFRESH),
        ], order='om_whatsapp_last_incoming desc', limit=limit * 10)
        return channels.filtered(lambda c: not c.om_whatsapp_partner_id.image_1920)[:limit]

    def _om_whatsapp_set_picture(self, number, data):
        """ The WhatsApp picture of ``number`` (base64, or False when the
        customer shows none): the photo of their contact when it has none, else
        of the conversation of an unknown number. """
        self.ensure_one()
        channel = self.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', '=', self.id),
            ('om_whatsapp_number', '=', number),
        ], limit=1)
        if not channel:
            return False
        channel.om_whatsapp_picture_date = fields.Datetime.now()
        if not data or not self.fetch_pictures:
            return False
        partner = channel.om_whatsapp_partner_id.sudo()
        try:
            with self.env.cr.savepoint():
                if not partner:
                    channel.image_128 = data
                elif not partner.image_1920:
                    partner.image_1920 = data
                    # the conversation shows it: its open pages get the new avatar
                    Store(bus_channel=channel).add(channel, ['avatar_cache_key'])
        except Exception as error:  # noqa: BLE001
            _logger.info("WhatsApp picture of %s not kept: %s", number, error)
            return False
        return True

    @api.model
    def _cron_om_whatsapp_pictures(self, limit=20):
        """ The providers that read the pictures from the server
        (``_om_whatsapp_picture_<provider>(number)``: base64 or False). """
        for account in self.search([('fetch_pictures', '=', True)]):
            fetch = getattr(account, f'_om_whatsapp_picture_{account.provider}', None)
            if not fetch:
                continue
            for channel in account._om_whatsapp_pictures_due(limit=limit):
                try:
                    data = fetch(channel.om_whatsapp_number)
                except Exception as error:  # noqa: BLE001
                    _logger.info("WhatsApp picture of %s not read: %s", channel.om_whatsapp_number, error)
                    data = False
                account._om_whatsapp_set_picture(channel.om_whatsapp_number, data)

    # ------------------------------------------------------------
    # PROVIDER CONTRACT: RECEIVING
    # ------------------------------------------------------------

    def _om_whatsapp_format_number(self, number):
        self.ensure_one()
        return self.env.user._phone_format(number=number, country=self.company_id.country_id) or number

    def _om_whatsapp_find_partner(self, number):
        self.ensure_one()
        return self.env['res.partner'].sudo().search(
            [('phone_sanitized', '=', number), ('company_id', 'in', [False, self.company_id.id])], limit=1)

    def _om_whatsapp_find_document(self, number, quoted_id=False):
        """ The document a message of ``number`` belongs to: the one of the
        message it quotes, else the one of the last message sent to that
        number within the reply window. """
        self.ensure_one()
        message = self.env['mail.message']
        if quoted_id:
            message = message.sudo().search([
                ('om_whatsapp_account_id', '=', self.id), ('om_whatsapp_id', '=', quoted_id),
                ('model', 'not in', [False, 'discuss.channel']),
            ], limit=1)
        if not message and self.reply_days > 0:
            message = self.env['mail.notification'].sudo().search([
                ('notification_type', '=', 'om_whatsapp'),
                ('om_whatsapp_number', '=', number),
                ('notification_status', 'in', ('pending', 'sent')),
                ('mail_message_id.om_whatsapp_account_id', '=', self.id),
                ('mail_message_id.model', 'not in', [False, 'discuss.channel']),
                ('mail_message_id.date', '>=', fields.Datetime.now() - timedelta(days=self.reply_days)),
            ], order='id desc', limit=1).mail_message_id
        if not message or message.model not in self.env:
            return None
        document = self.env[message.model].sudo().browse(message.res_id).exists()
        return document if document and hasattr(document, 'message_post') else None

    def _om_whatsapp_find_sent(self, number, body, whatsapp_id):
        """ A message of the phone may be one Odoo just sent, before the
        provider gave its id: give it the id instead of logging it twice. """
        self.ensure_one()
        notifications = self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_whatsapp'),
            ('om_whatsapp_number', '=', number),
            # process: a browser is sending it, and has not told its id yet
            ('notification_status', 'in', ('ready', 'process', 'pending', 'sent')),
            ('mail_message_id.om_whatsapp_account_id', '=', self.id),
            ('mail_message_id.om_whatsapp_id', '=', False),
            ('mail_message_id.date', '>=', fields.Datetime.now() - timedelta(minutes=10)),
        ], order='id desc')
        sent = notifications.filtered(lambda n: n.mail_message_id._om_whatsapp_text() == (body or '').strip())[:1]
        if not sent:
            return None
        sent.mail_message_id.om_whatsapp_id = whatsapp_id or False
        sent._om_whatsapp_set_status('sent')
        return sent.mail_message_id

    def _om_whatsapp_accepts(self, number, quoted_id=False):
        """ Whether a message of ``number`` is kept: a contact, a chat about a
        document, or any number when the account keeps the unknown ones. """
        self.ensure_one()
        return bool(self.receive_unknown or self._om_whatsapp_find_partner(number)
                    or self._om_whatsapp_find_document(number, quoted_id))

    def _om_whatsapp_receive(self, number, body='', whatsapp_id=False, attachments=None, quoted_id=False, from_me=False,
                             profile_name=False, voice=False):
        """ Record a message of a chat of this account: received from
        ``number``, or sent to it from the phone itself when ``from_me``. It
        goes to the WhatsApp conversation with that number, as an answer to
        the message it quotes, and to the document it answers. A number Odoo
        does not know is skipped, unless the account keeps them.
        ``attachments`` is a list of (filename, content); ``voice`` makes them
        a voice message. ``profile_name`` is the name the contact gave
        themselves in WhatsApp. A message seen twice is kept once.

        :return: the mail.message of the conversation, or False when skipped
        """
        self.ensure_one()
        Message = self.env['mail.message'].sudo()
        if whatsapp_id:
            existing = Message.search([('om_whatsapp_account_id', '=', self.id), ('om_whatsapp_id', '=', whatsapp_id)], limit=1)
            if existing:
                return existing
        number = self._om_whatsapp_format_number(number)
        if from_me and (sent := self._om_whatsapp_find_sent(number, body, whatsapp_id)):
            return sent
        partner = self._om_whatsapp_find_partner(number)
        document = self._om_whatsapp_find_document(number, quoted_id)
        if not document and not partner and not self.receive_unknown:
            return False
        channel = self._om_whatsapp_get_channel(number, partner, profile_name=profile_name)
        channel._om_whatsapp_set_document(document)
        message = False
        for target in (document, channel):
            if not target:
                continue
            post_values = {'attachments': attachments or [], 'om_whatsapp_id': whatsapp_id or False}
            if target == channel and quoted_id:
                # shown in the conversation as an answer to the message it quotes
                post_values['parent_id'] = Message.search([
                    ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('om_whatsapp_id', '=', quoted_id),
                ], limit=1).id or False
            if from_me:
                posted = target._message_om_whatsapp(self, body, number, partner=partner, status='pending', **post_values)
            else:
                posted = target.message_post(
                    body=plaintext2html(body) if body else '',
                    message_type='om_whatsapp',
                    subtype_xmlid='mail.mt_comment',
                    author_id=partner.id,
                    email_from=None if partner else channel.name,
                    om_whatsapp_account_id=self.id,
                    **post_values,
                )
            if voice:
                posted.attachment_ids._set_voice_metadata()
            message = posted
        if not from_me:
            channel.om_whatsapp_last_incoming = fields.Datetime.now()
        return message

    def _om_whatsapp_receive_reaction(self, number, whatsapp_id, emoji, from_me=False):
        """ A reaction of the contact (or of the user, from the phone) to a
        message: shown on it in Odoo, on the document and in the conversation.
        One reaction per person, as in WhatsApp; no emoji takes it back. """
        self.ensure_one()
        messages = self.env['mail.message'].sudo().search(
            [('om_whatsapp_account_id', '=', self.id), ('om_whatsapp_id', '=', whatsapp_id)])
        if not messages:
            return False
        if from_me:
            partner = self.env.user.partner_id
        else:
            number = self._om_whatsapp_format_number(number)
            partner = self._om_whatsapp_find_partner(number)
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

    def _om_whatsapp_update_status(self, whatsapp_id, status, failure_reason=False):
        """ Status update of a sent message, by its WhatsApp id: on the
        document and in the conversation. """
        self.ensure_one()
        messages = self.env['mail.message'].sudo().search(
            [('om_whatsapp_account_id', '=', self.id), ('om_whatsapp_id', '=', whatsapp_id)])
        return messages._om_whatsapp_notifications()._om_whatsapp_set_status(status, failure_reason)

    def _om_whatsapp_receive_item(self, item):
        """ One item read from WhatsApp by a provider (the browser extension,
        the WhatsApp Bridge): a message, the status of one sent, a reaction.
        A message has its file in ``media`` ({name, data}, base64), or
        ``media_error``.

        :return: whether it was recorded
        """
        self.ensure_one()
        if item.get('kind') == 'status':
            status = ITEM_STATUS.get(item.get('status') or item.get('ack'))
            return bool(status and self._om_whatsapp_update_status(item['id'], status))
        if item.get('kind') == 'reaction':
            return self._om_whatsapp_receive_reaction(
                f"+{item.get('phone')}", item.get('message_id'), item.get('emoji'), from_me=bool(item.get('from_me')))
        if item.get('kind') != 'message' or not item.get('phone') or not item.get('id'):
            return False
        lines = [item.get('body') or '']
        if item.get('note'):
            lines.insert(0, f"[{item['note']}]")
        attachments = []
        if media := item.get('media'):
            attachments.append((media['name'], base64.b64decode(media['data'])))
        elif item.get('media_error'):
            if label := MEDIA_LABELS.get(item.get('type')):
                lines.insert(0, f"[{label}]")
            lines.append(_("(The file could not be read from WhatsApp: %(reason)s)", reason=item['media_error']))
        return bool(self._om_whatsapp_receive(
            f"+{item['phone']}",
            '\n'.join(line for line in lines if line),
            whatsapp_id=item['id'],
            attachments=attachments,
            quoted_id=item.get('quoted_id') or False,
            from_me=bool(item.get('from_me')),
            profile_name=item.get('name') or False,
            voice=item.get('type') == 'ptt' and bool(attachments),
        ))
