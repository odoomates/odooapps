import html
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class MailMessage(models.Model):
    """ A message of the Social Inbox is a mail.message of type
    ``om_social``. A sent one has an ``om_social`` notification per
    recipient, which holds its status: ready (queued), pending (sent), sent
    (delivered), is_read (read), exception (failed) or canceled. A received
    one has none. """
    _inherit = 'mail.message'

    message_type = fields.Selection(
        selection_add=[('om_social', 'Social Message')],
        ondelete={'om_social': lambda messages: messages.write({'message_type': 'comment'})})
    om_social_account_id = fields.Many2one(
        'om.social.account', string='Social Account', index='btree_not_null', ondelete='set null')
    om_social_message_id = fields.Char(
        'Channel Message ID', index='btree_not_null', copy=False, readonly=True,
        help="Id of the message in the channel, used to skip duplicates, match replies and status updates.")
    om_social_status = fields.Selection([
        ('received', 'Received'),
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('cancel', 'Cancelled'),
    ], string='Message Status', compute='_compute_om_social_status')
    om_social_receipt = fields.Selection(
        [('read', 'Read'), ('played', 'Played')], string='Receipt', readonly=True, copy=False,
        help="For a message received: what the channel was told, once a user read it in Discuss or played it.")
    om_social_has_error = fields.Boolean(
        'Has Sending Error', compute='_compute_om_social_has_error', search='_search_om_social_has_error')

    @api.depends('message_type', 'author_id', 'email_from', 'notification_ids.res_partner_id',
                 'notification_ids.om_social_address', 'om_social_account_id.channel')
    def _compute_display_name(self):
        """ A message of the Social Inbox has no subject: it is named by the
        other side of the chat. """
        social = self.filtered(lambda m: m.message_type == 'om_social' and not m.subject)
        super(MailMessage, self - social)._compute_display_name()
        for message in social:
            channel = message.sudo().om_social_account_id._om_social_channel_label() \
                if message.om_social_account_id else _("Message")
            notification = message._om_social_notifications()[:1]
            if notification:
                message.display_name = _("%(channel)s to %(contact)s", channel=channel,
                                         contact=notification.res_partner_id.name or notification.om_social_address)
            else:
                message.display_name = _("%(channel)s from %(contact)s", channel=channel,
                                         contact=message.author_id.name or message.email_from or _("unknown"))

    def _om_social_notifications(self):
        return self.sudo().notification_ids.filtered(lambda n: n.notification_type == 'om_social')

    @api.depends('message_type', 'notification_ids.notification_status', 'notification_ids.is_read')
    def _compute_om_social_status(self):
        for message in self:
            if message.message_type != 'om_social':
                message.om_social_status = False
                continue
            notification = message._om_social_notifications()[:1]
            message.om_social_status = notification._om_social_get_status() if notification else 'received'

    def _compute_om_social_has_error(self):
        failed = self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_social'),
            ('mail_message_id', 'in', self.ids),
            ('notification_status', '=', 'exception'),
        ]).mail_message_id
        for message in self:
            message.om_social_has_error = message in failed

    def _search_om_social_has_error(self, operator, operand):
        if operator != 'in':
            return NotImplemented
        return [('notification_ids', 'any', [
            ('notification_status', '=', 'exception'),
            ('notification_type', '=', 'om_social'),
        ])]

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model
    def _om_social_guarded_fields(self):
        """ The fields only the users of the account write: channel modules
        add theirs. """
        return {'om_social_account_id', 'om_social_message_id'}

    @api.model_create_multi
    def create(self, vals_list):
        """ A message of the Social Inbox is made by the users of its account,
        and only a provider knows its id in the channel: anyone else could
        fake a message of a customer, or catch the replies to a real one. """
        if not self.env.su:
            guarded = self._om_social_guarded_fields()
            for vals in vals_list:
                if vals.get('om_social_message_id'):
                    raise AccessError(_("Only the channel itself gives a message its id."))
                if vals.get('message_type') == 'om_social' or any(vals.get(name) for name in guarded):
                    self._om_social_check_account(vals.get('om_social_account_id'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and (vals.get('message_type') == 'om_social' or self._om_social_guarded_fields() & set(vals)):
            account_ids = set(self.om_social_account_id.ids)
            if vals.get('om_social_account_id'):
                account_ids.add(vals['om_social_account_id'])
            for account_id in account_ids or {False}:
                self._om_social_check_account(account_id)
        return super().write(vals)

    @api.model
    def _om_social_check_account(self, account_id):
        # sudo: a user outside the account may not read it, and is refused all the same
        account = self.env['om.social.account'].sudo().browse(account_id).exists()
        if not account or self.env.user not in account.user_ids:
            raise AccessError(_("You are not allowed to make messages of this account."))

    def _om_social_text(self):
        """ The text to send, as typed: the body is its html, made of
        paragraphs, line breaks and links. """
        self.ensure_one()
        text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', self.body or '')
        text = re.sub(r'<br\s*/?>', '\n', text)
        return html.unescape(re.sub(r'<[^>]+>', '', text)).strip()

    def _om_social_add_notification(self, address, partner=False, status='ready', failure_type=False,
                                    failure_reason=False):
        """ Make this message a message to ``address`` (an address, or the
        user ID of a customer whose address is unknown): its notification
        holds its status. """
        self.ensure_one()
        partner = partner or self.env['res.partner']
        account = self.om_social_account_id or self.env['om.social.account']
        values = {
            'author_id': self.author_id.id,
            'om_social_address': account._om_social_clean_address(address) or False,
            'notification_type': 'om_social',
            'notification_status': status,
            'failure_type': failure_type,
            'failure_reason': failure_reason,
            # read by the customer, for the ticks; a user reads it in the Inbox
            'is_read': bool(partner) and not partner.partner_share,
        }
        # a user following the document got an Inbox notification already
        if existing := self.sudo().notification_ids.filtered(lambda n: partner and n.res_partner_id == partner):
            existing.write(values)
            return existing
        return self.env['mail.notification'].sudo().create(dict(values, mail_message_id=self.id, res_partner_id=partner.id))

    def _om_social_copies(self):
        """ This message and its copies (on the document and in the
        conversation): the messages of the account with its id. """
        self.ensure_one()
        return self.sudo().search([
            ('om_social_account_id', '=', self.om_social_account_id.id),
            ('om_social_message_id', '=', self.om_social_message_id),
        ])

    def _om_social_quoted(self):
        """ The message this one answers (a reply in Discuss): {id, from_me}
        for the provider to send it as a quoted reply, or False. """
        self.ensure_one()
        parent = self.sudo().parent_id
        if not parent.om_social_message_id:
            return False
        # sent from Odoo, or from the phone by a user
        author = parent.author_id
        from_me = bool(parent._om_social_notifications()) or bool(author.user_ids and not author.partner_share)
        return {'id': parent.om_social_message_id, 'from_me': from_me}

    def _om_social_chat(self):
        """ (address of the chat, whether the message was sent from Odoo): the
        address of its notification, else the one of its conversation; the
        user ID of the customer when the address is unknown. """
        self.ensure_one()
        copies = self._om_social_copies()
        notification = copies._om_social_notifications()[:1]
        if notification:
            return notification.om_social_address or False, True
        channel = self.env['discuss.channel'].sudo().browse(
            copies.filtered(lambda m: m.model == 'discuss.channel').mapped('res_id')).exists()[:1]
        return (channel._om_social_recipient() if channel else False), False

    # ------------------------------------------------------------
    # RECEIPTS: read in Discuss, played in Odoo
    # ------------------------------------------------------------

    def _om_social_send_receipts(self, kind):
        """ Tell the channel that the received messages among these were read
        (``kind`` 'read') or played ('played': a voice message), once: their
        copies are marked too. A receipt that cannot go never stops the
        reading. """
        rank = {False: 0, 'read': 1, 'played': 2}
        received = self.sudo().filtered(
            lambda m: m.message_type == 'om_social' and m.om_social_message_id and m.om_social_account_id
            and rank[m.om_social_receipt] < rank[kind] and not m._om_social_notifications())
        chats = {}
        for message in received:
            address, from_me = message._om_social_chat()
            if address and not from_me:
                chats.setdefault((message.om_social_account_id, address), {})[message.om_social_message_id] = message
        for (account, address), by_id in chats.items():
            if self.env.user not in account.user_ids:
                continue
            copies = self.sudo().search([('om_social_account_id', '=', account.id),
                                         ('om_social_message_id', 'in', list(by_id))])
            if account._om_social_send_receipt(address, list(by_id), kind):
                copies.filtered(lambda m: rank[m.om_social_receipt] < rank[kind]).om_social_receipt = kind

    @api.model
    def om_social_played(self, attachment_id):
        """ A voice message played in Odoo, by the id of its file: the channel
        shows it played. """
        message = self.sudo().search([
            ('attachment_ids', 'in', [attachment_id]), ('message_type', '=', 'om_social'),
            ('om_social_message_id', '!=', False),
        ], limit=1)
        if message:
            message.with_env(self.env)._om_social_send_receipts('played')
        return True

    # ------------------------------------------------------------
    # REACTIONS
    # ------------------------------------------------------------

    def _message_reaction(self, content, action, partner, guest, store=None):
        """ A user of the account who reacts to a message in Odoo reacts in
        the channel too. One reaction per person: a new one replaces the one
        before, on the copies of the message as well; taking it back takes it
        back there. """
        account = self.om_social_account_id
        if (self.message_type != 'om_social' or not self.om_social_message_id or not account or guest
                or partner not in account.user_ids.partner_id):
            return super()._message_reaction(content, action, partner, guest, store=store)
        Reaction = self.env['mail.message.reaction'].sudo()
        if action == 'add':
            before = Reaction.search([('message_id', '=', self.id), ('partner_id', '=', partner.id), ('content', '!=', content)])
            contents = set(before.mapped('content'))
            before.unlink()
            for old in contents:
                self._bus_send_reaction_group(old)
        super()._message_reaction(content, action, partner, guest, store=store)
        emoji = Reaction.search([('message_id', '=', self.id), ('partner_id', '=', partner.id)], limit=1).content or ''
        for copy in self._om_social_copies() - self:
            previous = Reaction.search([('message_id', '=', copy.id), ('partner_id', '=', partner.id)])
            if previous.content == emoji and len(previous) <= 1:
                continue
            contents = set(previous.mapped('content'))
            previous.unlink()
            if emoji:
                Reaction.create({'message_id': copy.id, 'partner_id': partner.id, 'content': emoji})
                contents.add(emoji)
            for changed in contents:
                copy._bus_send_reaction_group(changed)
        account._om_social_send_reaction(self, emoji)

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------

    def action_open_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_om_social_retry(self):
        """ Send the failed or cancelled messages again, by the author. """
        self.check_access('read')
        notifications = self._om_social_notifications().filtered(
            lambda n: n.notification_status in ('exception', 'canceled') and n.om_social_address)
        if not notifications:
            raise UserError(_("There is no failed message to send again."))
        notifications.write({'notification_status': 'ready', 'failure_type': False, 'failure_reason': False})
        notifications.mail_message_id._notify_message_notification_update()
        return notifications._om_social_send()

    def action_om_social_cancel(self):
        self.check_access('read')
        self._om_social_notifications().filtered(
            lambda n: n.notification_status == 'ready')._om_social_set_status('cancel')
