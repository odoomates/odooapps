import html
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class MailMessage(models.Model):
    """ A WhatsApp message is a mail.message of type ``om_whatsapp``. A sent
    one has a ``om_whatsapp`` notification per recipient, which holds its
    status: ready (queued), pending (sent), sent (delivered), is_read (read),
    exception (failed) or canceled. A received one has none. """
    _inherit = 'mail.message'

    message_type = fields.Selection(
        selection_add=[('om_whatsapp', 'WhatsApp')],
        ondelete={'om_whatsapp': lambda messages: messages.write({'message_type': 'comment'})})
    om_whatsapp_account_id = fields.Many2one(
        'om.whatsapp.account', string='WhatsApp Account', index='btree_not_null', ondelete='set null')
    om_whatsapp_id = fields.Char(
        'WhatsApp Message ID', index='btree_not_null', copy=False, readonly=True,
        help="Id of the message in WhatsApp, used to skip duplicates, match replies and status updates.")
    om_whatsapp_template_id = fields.Many2one(
        'om.whatsapp.template', string='WhatsApp Template', index='btree_not_null', ondelete='set null', readonly=True,
        help="The template the message was made from: a provider whose templates are approved upstream sends that.")
    om_whatsapp_status = fields.Selection([
        ('received', 'Received'),
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('cancel', 'Cancelled'),
    ], string='WhatsApp Status', compute='_compute_om_whatsapp_status')
    om_whatsapp_receipt = fields.Selection(
        [('read', 'Read'), ('played', 'Played')], string='WhatsApp Receipt', readonly=True, copy=False,
        help="For a message received: what WhatsApp was told, once a user read it in Discuss or played it.")
    has_om_whatsapp_error = fields.Boolean(
        'Has WhatsApp Error', compute='_compute_has_om_whatsapp_error', search='_search_has_om_whatsapp_error')

    @api.depends('message_type', 'author_id', 'email_from', 'notification_ids.res_partner_id', 'notification_ids.om_whatsapp_number')
    def _compute_display_name(self):
        """ A WhatsApp message has no subject: it is named by the other side
        of the chat. """
        whatsapp = self.filtered(lambda m: m.message_type == 'om_whatsapp' and not m.subject)
        super(MailMessage, self - whatsapp)._compute_display_name()
        for message in whatsapp:
            notification = message._om_whatsapp_notifications()[:1]
            if notification:
                message.display_name = _("WhatsApp to %(contact)s",
                                         contact=notification.res_partner_id.name or notification.om_whatsapp_number)
            else:
                message.display_name = _("WhatsApp from %(contact)s",
                                         contact=message.author_id.name or message.email_from or _("unknown"))

    def _om_whatsapp_notifications(self):
        return self.sudo().notification_ids.filtered(lambda n: n.notification_type == 'om_whatsapp')

    @api.depends('message_type', 'notification_ids.notification_status', 'notification_ids.is_read')
    def _compute_om_whatsapp_status(self):
        for message in self:
            if message.message_type != 'om_whatsapp':
                message.om_whatsapp_status = False
                continue
            notification = message._om_whatsapp_notifications()[:1]
            message.om_whatsapp_status = notification._om_whatsapp_get_status() if notification else 'received'

    def _compute_has_om_whatsapp_error(self):
        failed = self.env['mail.notification'].sudo().search([
            ('notification_type', '=', 'om_whatsapp'),
            ('mail_message_id', 'in', self.ids),
            ('notification_status', '=', 'exception'),
        ]).mail_message_id
        for message in self:
            message.has_om_whatsapp_error = message in failed

    def _search_has_om_whatsapp_error(self, operator, operand):
        if operator != 'in':
            return NotImplemented
        return [('notification_ids', 'any', [
            ('notification_status', '=', 'exception'),
            ('notification_type', '=', 'om_whatsapp'),
        ])]

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """ A WhatsApp message is made by the users of its account, and only a
        provider knows its WhatsApp id: anyone else could fake a message of
        a customer, or catch the replies to a real one. """
        if not self.env.su:
            for vals in vals_list:
                if vals.get('om_whatsapp_id'):
                    raise AccessError(_("Only WhatsApp itself gives a message its id."))
                if vals.get('message_type') == 'om_whatsapp' or vals.get('om_whatsapp_account_id') \
                        or vals.get('om_whatsapp_template_id'):
                    self._om_whatsapp_check_account(vals.get('om_whatsapp_account_id'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and (vals.get('message_type') == 'om_whatsapp'
                                or {'om_whatsapp_account_id', 'om_whatsapp_id', 'om_whatsapp_template_id'} & set(vals)):
            account_ids = set(self.om_whatsapp_account_id.ids)
            if vals.get('om_whatsapp_account_id'):
                account_ids.add(vals['om_whatsapp_account_id'])
            for account_id in account_ids or {False}:
                self._om_whatsapp_check_account(account_id)
        return super().write(vals)

    @api.model
    def _om_whatsapp_check_account(self, account_id):
        # sudo: a user outside the account may not read it, and is refused all the same
        account = self.env['om.whatsapp.account'].sudo().browse(account_id).exists()
        if not account or self.env.user not in account.user_ids:
            raise AccessError(_("You are not allowed to make WhatsApp messages of this account."))

    def _om_whatsapp_text(self):
        """ The text to send, as typed: the body is its html, made of
        paragraphs, line breaks and links. """
        self.ensure_one()
        text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', self.body or '')
        text = re.sub(r'<br\s*/?>', '\n', text)
        return html.unescape(re.sub(r'<[^>]+>', '', text)).strip()

    def _om_whatsapp_add_notification(self, number, partner=False, status='ready', failure_type=False, failure_reason=False):
        """ Make this message a WhatsApp message to ``number``: its
        notification holds its status. """
        self.ensure_one()
        partner = partner or self.env['res.partner']
        values = {
            'author_id': self.author_id.id,
            'om_whatsapp_number': number,
            'notification_type': 'om_whatsapp',
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

    def _om_whatsapp_copies(self):
        """ This message and its copies (on the document and in the
        conversation): the messages of the account with its WhatsApp id. """
        self.ensure_one()
        return self.sudo().search([
            ('om_whatsapp_account_id', '=', self.om_whatsapp_account_id.id), ('om_whatsapp_id', '=', self.om_whatsapp_id),
        ])

    def _om_whatsapp_quoted(self):
        """ The WhatsApp message this one answers (a reply in Discuss): {id,
        from_me} for the provider to send it as a quoted reply, or False. """
        self.ensure_one()
        parent = self.sudo().parent_id
        if not parent.om_whatsapp_id:
            return False
        # sent from Odoo, or from the phone by a user
        author = parent.author_id
        from_me = bool(parent._om_whatsapp_notifications()) or bool(author.user_ids and not author.partner_share)
        return {'id': parent.om_whatsapp_id, 'from_me': from_me}

    def _om_whatsapp_chat(self):
        """ (number of the chat, whether the message was sent from Odoo): the
        number of its notification, else the one of its conversation. """
        self.ensure_one()
        copies = self._om_whatsapp_copies()
        notification = copies._om_whatsapp_notifications()[:1]
        if notification:
            return notification.om_whatsapp_number, True
        channel = self.env['discuss.channel'].sudo().browse(
            copies.filtered(lambda m: m.model == 'discuss.channel').mapped('res_id')).exists()[:1]
        return channel.om_whatsapp_number or False, False

    # ------------------------------------------------------------
    # RECEIPTS: read in Discuss, played in Odoo
    # ------------------------------------------------------------

    def _om_whatsapp_send_receipts(self, kind):
        """ Tell WhatsApp that the received messages among these were read
        (``kind`` 'read': blue ticks) or played ('played': the blue microphone
        of a voice message), once: their copies are marked too. A receipt that
        cannot go never stops the reading. """
        rank = {False: 0, 'read': 1, 'played': 2}
        received = self.sudo().filtered(
            lambda m: m.message_type == 'om_whatsapp' and m.om_whatsapp_id and m.om_whatsapp_account_id
            and rank[m.om_whatsapp_receipt] < rank[kind] and not m._om_whatsapp_notifications())
        chats = {}
        for message in received:
            number, from_me = message._om_whatsapp_chat()
            if number and not from_me:
                chats.setdefault((message.om_whatsapp_account_id, number), {})[message.om_whatsapp_id] = message
        for (account, number), by_id in chats.items():
            if self.env.user not in account.user_ids:
                continue
            copies = self.sudo().search([('om_whatsapp_account_id', '=', account.id),
                                         ('om_whatsapp_id', 'in', list(by_id))])
            if account._om_whatsapp_send_receipt(number, list(by_id), kind):
                copies.filtered(lambda m: rank[m.om_whatsapp_receipt] < rank[kind]).om_whatsapp_receipt = kind

    @api.model
    def om_whatsapp_played(self, attachment_id):
        """ A voice message played in Odoo, by the id of its file: WhatsApp
        shows it played. """
        message = self.sudo().search([
            ('attachment_ids', 'in', [attachment_id]), ('message_type', '=', 'om_whatsapp'),
            ('om_whatsapp_id', '!=', False),
        ], limit=1)
        if message:
            message.with_env(self.env)._om_whatsapp_send_receipts('played')
        return True

    # ------------------------------------------------------------
    # REACTIONS
    # ------------------------------------------------------------

    def _message_reaction(self, content, action, partner, guest, store=None):
        """ A user of the account who reacts to a WhatsApp message in Odoo
        reacts in WhatsApp too. WhatsApp keeps one reaction per person: a new
        one replaces the one before, on the copies of the message as well;
        taking it back takes it back there. """
        account = self.om_whatsapp_account_id
        if (self.message_type != 'om_whatsapp' or not self.om_whatsapp_id or not account or guest
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
        for copy in self._om_whatsapp_copies() - self:
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
        account._om_whatsapp_send_reaction(self, emoji)

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

    def action_om_whatsapp_retry(self):
        """ Send the failed or cancelled messages again, by the author. """
        self.check_access('read')
        notifications = self._om_whatsapp_notifications().filtered(
            lambda n: n.notification_status in ('exception', 'canceled') and n.om_whatsapp_number)
        if not notifications:
            raise UserError(_("There is no failed WhatsApp message to send again."))
        notifications.write({'notification_status': 'ready', 'failure_type': False, 'failure_reason': False})
        notifications.mail_message_id._notify_message_notification_update()
        return notifications._om_whatsapp_send()

    def action_om_whatsapp_cancel(self):
        self.check_access('read')
        self._om_whatsapp_notifications().filtered(
            lambda n: n.notification_status == 'ready')._om_whatsapp_set_status('cancel')
