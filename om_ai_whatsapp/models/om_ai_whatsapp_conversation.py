import hashlib
import hmac
import json
import logging
import re
import secrets
import unicodedata
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

HISTORY_SIZE = 20
CODE_MINUTES = 15
CODE_TRIES = 3
LOCK_HOURS = 1
PENDING_HOURS = 24
LEVELS = [('0', 'Unknown'), ('1', 'Known Number'), ('2', 'Private Data')]
STOP_WORDS = {'stop', 'unsubscribe', 'opt out', 'optout', 'stop all'}
START_WORDS = {'start', 'unstop', 'subscribe'}
# a customer confirms a pending action with one of these, in many languages
YES_WORDS = {
    'yes', 'y', 'yeah', 'yep', 'yup', 'ok', 'okay', 'k', 'confirm', 'confirmed', 'sure', 'go ahead', 'yes please',
    'si', 'sí', 'claro', 'vale', 'oui', 'ja', 'jawohl', 'da', 'sim', 'evet', 'tak', 'ano', 'igen', 'jo', 'kyllä',
    'haan', 'han', 'ha', 'haa', 'ji', 'ji haan', 'theek hai', 'ya', 'iya', 'ndiyo', 'ναι', 'да', 'так', 'כן',
    'نعم', 'ايوه', 'أيوه', 'aiwa', 'بله', 'हाँ', 'हां', 'ஆம்', 'అవును', 'ಹೌದು', 'അതെ', 'হ্যাঁ', 'ہاں', 'はい',
    '네', '예', '是', '是的', '好', '好的', 'ใช่', 'vâng', 'có', 'oo', 'opo',
}
EMOJI_YES = {'\U0001F44D', '✅', '✔', '\U0001F44C'}


def normalise(text):
    """ Lower case, without punctuation around, single spaces. """
    text = unicodedata.normalize('NFC', (text or '').strip().lower())
    text = re.sub(r'[\s]+', ' ', text)
    return text.strip(' .!?,;:¡¿،؟。！')


def is_yes(text):
    raw = (text or '').strip()
    if raw and all(char in EMOJI_YES or char in '️ ' for char in raw):
        return True
    text = normalise(text)
    if text in YES_WORDS:
        return True
    first = re.split(r'[\s,.!]+', text, maxsplit=1)[0]
    return first in {'yes', 'si', 'sí', 'oui', 'ja', 'da', 'sim', 'haan', 'ok', 'okay', 'confirm', 'نعم', 'हाँ', 'हां'}


class OmAiWhatsappConversation(models.Model):
    """ What the assistant knows of one WhatsApp conversation: who the
    customer is, how far they are trusted (the level, always computed here
    and never by the AI), the quotation being built, a confirmation it waits
    for, the email code, and whether a person took over. """
    _name = 'om.ai.whatsapp.conversation'
    _description = 'WhatsApp AI Conversation'
    _order = 'last_message_date desc, id desc'
    _rec_name = 'channel_id'

    channel_id = fields.Many2one('discuss.channel', string='Conversation', required=True, ondelete='cascade',
                                 index=True, readonly=True)
    account_id = fields.Many2one('om.social.account', string='WhatsApp Account', required=True,
                                 ondelete='cascade', index=True, readonly=True)
    company_id = fields.Many2one(related='account_id.company_id', store=True)
    number = fields.Char('WhatsApp Number', readonly=True)
    profile_name = fields.Char(related='channel_id.om_social_profile_name', string='Profile Name')
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True, index='btree_not_null',
                                 help="The contact the assistant serves: the only contact with this number, or "
                                      "the one made in this conversation.")
    partner_created = fields.Boolean('Contact Made Here', readonly=True)
    level = fields.Selection(LEVELS, compute='_compute_level', string='Level',
                             help="Unknown: general questions only. Known number: own quotations, payment links "
                                  "and order status. Private data: also invoices, balance and addresses (after the "
                                  "email code when the account asks for one).")
    state = fields.Selection([
        ('ai', 'Assistant'),
        ('human', 'Person'),
        ('stopped', 'Opted Out'),
    ], default='ai', required=True, readonly=True, index=True)
    handover_user_id = fields.Many2one('res.users', string='Handled By', readonly=True)
    handover_reason = fields.Char(readonly=True)
    order_id = fields.Many2one('sale.order', string='Current Quotation', readonly=True)
    order_ids = fields.One2many('sale.order', 'om_ai_whatsapp_conversation_id', string='Orders')
    order_count = fields.Integer(compute='_compute_order_count')
    pending_actions = fields.Json(readonly=True, copy=False)
    pending_date = fields.Datetime(readonly=True, copy=False)
    code_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    code_expiry = fields.Datetime(readonly=True, copy=False)
    code_tries = fields.Integer(readonly=True, copy=False)
    locked_until = fields.Datetime('Code Locked Until', readonly=True, copy=False)
    reply_count = fields.Integer('AI Replies', readonly=True)
    handover_count = fields.Integer('Hand-overs', readonly=True)
    last_message_date = fields.Datetime(readonly=True)
    job_ids = fields.One2many('om.ai.whatsapp.job', 'conversation_id', string='Jobs')

    _channel_unique = models.Constraint('UNIQUE(channel_id)', 'A conversation has one assistant record.')

    def _compute_order_count(self):
        for conversation in self:
            conversation.order_count = len(conversation.order_ids)

    def _compute_level(self):
        for conversation in self:
            conversation.level = str(conversation.sudo()._om_ai_level())

    @api.model
    def _om_ai_get(self, channel):
        conversation = self.search([('channel_id', '=', channel.id)], limit=1)
        if not conversation:
            conversation = self.create({
                'channel_id': channel.id,
                'account_id': channel.om_social_account_id.id,
                'number': channel.om_social_address,
            })
        return conversation

    # ------------------------------------------------------------
    # WHO IS THE CUSTOMER: computed in code, never by the AI
    # ------------------------------------------------------------

    def _om_ai_number_partners(self):
        """ The contacts with the number of this conversation (at most 2). """
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        domain = [('company_id', 'in', [False, self.account_id.company_id.id]),
                  ('id', 'not in', self.env['res.users'].sudo().with_context(active_test=False).search(
                      [('om_ai_whatsapp_assistant', '=', True)]).partner_id.ids)]
        partners = Partner.search([('phone_sanitized', '=', self.number), *domain], limit=2)
        if not partners and self.number:
            partners = Partner.search([('phone_mobile_search', '=', self.number), *domain], limit=2)
        return partners

    def _om_ai_customer(self):
        """ The contact the assistant serves, or an empty recordset: a number
        on several contacts is nobody, unless the contact was made here. """
        self.ensure_one()
        if self.partner_created and self.partner_id.active:
            return self.partner_id
        partners = self._om_ai_number_partners()
        return partners if len(partners) == 1 else self.env['res.partner']

    def _om_ai_sync_customer(self):
        for conversation in self.sudo():
            partner = conversation._om_ai_customer()
            if partner != conversation.partner_id:
                conversation.partner_id = partner

    def _om_ai_level(self):
        """ 0 unknown, 1 known number, 2 private data allowed: verified by
        the email code, or a known number when the account asks no code. """
        self.ensure_one()
        partner = self._om_ai_customer()
        if not partner:
            return 0
        if not self.account_id.om_ai_email_code:
            return 2
        if partner._om_ai_whatsapp_is_verified(self.number, self.account_id.om_ai_verify_days):
            return 2
        return 1

    def _om_ai_scope_domain(self, level=None, field='partner_id'):
        """ The documents the customer may see: their own (and their delivery
        and invoice addresses), or with a verified number and the setting,
        those of their whole company. """
        self.ensure_one()
        partner = self._om_ai_customer()
        if not partner:
            return [(field, '=', 0)]
        level = self._om_ai_level() if level is None else level
        if level >= 2 and self.account_id.om_ai_document_scope == 'commercial':
            return [(field, 'child_of', partner.commercial_partner_id.id)]
        own = partner | partner.child_ids.filtered(lambda p: p.type in ('delivery', 'invoice', 'other'))
        return [(field, 'in', own.ids)]

    def _om_ai_lang(self):
        self.ensure_one()
        partner = self._om_ai_customer()
        return partner.lang or self.account_id.company_id.partner_id.lang or self.env.lang or 'en_US'

    def _om_ai_env(self):
        """ This conversation, as seen by the assistant user, in the language of the customer. """
        self.ensure_one()
        user = self.account_id._om_ai_get_user()
        company = self.account_id.company_id
        return self.with_user(user).with_company(company).with_context(
            allowed_company_ids=company.ids,
            lang=self._om_ai_lang(),
            om_ai_whatsapp_conversation_id=self.id,
        )

    # ------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------

    def _om_ai_is_opted_out(self):
        self.ensure_one()
        return bool(self.env['phone.blacklist'].sudo().search_count([('number', '=', self.number)], limit=1))

    def _om_ai_send(self, text, attachments=None, force=False):
        """ Send ``text`` (plain text, WhatsApp style) and the attachments
        (ir.attachment) to the customer, as the assistant. """
        self.ensure_one()
        if not text and not attachments:
            return self.env['mail.message']
        if not force and self._om_ai_is_opted_out():
            return self.env['mail.message']
        conversation = self.sudo()
        account = conversation.account_id
        channel = conversation.channel_id
        user = account._om_ai_get_user()
        attachment_ids = []
        for attachment in attachments or []:
            attachment_ids.append(attachment.sudo().copy({'res_model': 'discuss.channel', 'res_id': channel.id}).id
                                  if attachment.res_model != 'discuss.channel' else attachment.id)
        message = channel.with_context(om_ai_whatsapp_sending=True)._message_om_social(
            account, text or '', channel._om_social_recipient(), partner=conversation.partner_id,
            author_id=user.partner_id.id, attachment_ids=attachment_ids,
        )
        notifications = message._om_social_notifications().filtered(lambda n: n.notification_status == 'ready')
        if notifications:
            try:
                with self.env.cr.savepoint():
                    account._om_ai_deliver(notifications)
            except Exception as error:  # noqa: BLE001 - the message stays in Discuss to send again
                _logger.warning("WhatsApp assistant message %s not sent: %s", message.id, error)
                notifications._om_social_set_status('failed', str(error))
        return message

    @staticmethod
    def _om_ai_whatsapp_style(text):
        """ Markdown of the AI to WhatsApp formatting. """
        text = (text or '').strip()
        text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
        text = re.sub(r'__(.+?)__', r'_\1_', text)
        text = re.sub(r'^#{1,6}\s*(.+)$', r'*\1*', text, flags=re.M)
        text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'\1: \2', text)
        return text

    def _om_ai_note(self, body, author=None):
        """ A note in the conversation for the users, not sent to WhatsApp. """
        self.ensure_one()
        author = author or self.account_id._om_ai_get_user().partner_id
        self.channel_id.sudo().message_post(
            body=Markup('<p>%s</p>') % body, message_type='notification', subtype_xmlid='mail.mt_note',
            author_id=author.id)

    # ------------------------------------------------------------
    # HAND-OVER
    # ------------------------------------------------------------

    def _om_ai_salesperson(self):
        self.ensure_one()
        partner = self._om_ai_customer()
        user = partner.user_id or partner.commercial_partner_id.user_id
        if not user or user.share or not user.active:
            user = self.account_id.om_ai_salesperson_id
        return user or self.account_id.user_ids[:1]

    def _om_ai_hand_over(self, reason, user=None, message=None):
        """ A person answers from now on: the salesperson (or ``user``) is
        added to the conversation and notified; the assistant stops. """
        for conversation in self.sudo():
            user = user or conversation._om_ai_salesperson()
            conversation.write({
                'state': 'human',
                'handover_user_id': user.id if user else False,
                'handover_reason': reason,
                'handover_count': conversation.handover_count + 1,
                'pending_actions': False,
            })
            channel = conversation.channel_id
            if user and user.partner_id not in channel.channel_member_ids.partner_id:
                channel._add_members(users=user, post_joined_message=False)
            conversation._om_ai_note(self.env._(
                "The assistant handed this conversation over to %(user)s: %(reason)s",
                user=user.name if user else self.env._('the team'), reason=reason))
            if message:
                conversation._om_ai_send(message)
            if user and user != self.env.user:
                record = conversation.partner_id or user.partner_id
                record.sudo().message_notify(
                    partner_ids=user.partner_id.ids,
                    subject=self.env._('WhatsApp: %s needs a person', channel.name),
                    body=Markup('<p>%s</p><p>%s</p>') % (
                        self.env._('The WhatsApp assistant handed over the conversation with %s.', channel.name),
                        reason),
                    model_description=self.env._('WhatsApp conversation'),
                )

    def _om_ai_take_over(self, user):
        for conversation in self.sudo().filtered(lambda c: c.state != 'human'):
            conversation.write({
                'state': 'human', 'handover_user_id': user.id, 'pending_actions': False,
                'handover_reason': self.env._('taken over by %s', user.name),
                'handover_count': conversation.handover_count + 1,
            })
            conversation._om_ai_note(self.env._("%s took over: the assistant does not answer.", user.name),
                                     author=user.partner_id)

    def _om_ai_give_back(self, user):
        for conversation in self.sudo().filtered(lambda c: c.state == 'human'):
            conversation.write({'state': 'ai', 'handover_reason': False})
            conversation._om_ai_note(self.env._("%s gave the conversation back to the assistant.", user.name),
                                     author=user.partner_id)

    def action_take_over(self):
        for conversation in self:
            conversation.account_id._om_social_check_user()
        self._om_ai_take_over(self.env.user)
        return True

    def action_give_back(self):
        for conversation in self:
            conversation.account_id._om_social_check_user()
        self._om_ai_give_back(self.env.user)
        return True

    def action_open_channel(self):
        self.ensure_one()
        return self.channel_id.open_chat_window_action()

    def action_view_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        action['domain'] = [('om_ai_whatsapp_conversation_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    # ------------------------------------------------------------
    # VERIFICATION BY EMAIL CODE
    # ------------------------------------------------------------

    def _om_ai_hash_code(self, code):
        secret = self.env['ir.config_parameter'].sudo().get_str('database.secret') or ''
        return hmac.new(secret.encode(), f'{self.id}:{code}'.encode(), hashlib.sha256).hexdigest()

    def _om_ai_send_code(self):
        """ Mail a 6-digit code to the email already on the contact. """
        self.ensure_one()
        conversation = self.sudo()
        partner = conversation._om_ai_customer()
        now = fields.Datetime.now()
        if not partner:
            raise UserError(self.env._('The customer is not known yet.'))
        if conversation.locked_until and conversation.locked_until > now:
            raise UserError(self.env._('Too many wrong codes: verification is locked until %s (UTC).',
                                       fields.Datetime.to_string(conversation.locked_until)[:16]))
        if not partner.email or '@' not in partner.email:
            raise UserError(self.env._('There is no email on the contact: a person has to verify this customer.'))
        code = f'{secrets.randbelow(10 ** 6):06d}'
        conversation.write({
            'code_hash': conversation._om_ai_hash_code(code),
            'code_expiry': now + timedelta(minutes=CODE_MINUTES),
            'code_tries': 0,
        })
        template = self.env.ref('om_ai_whatsapp.mail_template_verification_code')
        template.sudo().with_company(conversation.account_id.company_id).with_context(
            om_ai_whatsapp_code=code, lang=partner.lang).send_mail(
            partner.id, force_send=True, email_layout_xmlid='mail.mail_notification_light',
            # not on the contact: the code stays out of its chatter
            email_values={'model': False, 'res_id': False})
        name, _sep, domain = partner.email.strip().partition('@')
        return f'{name[:1]}***@{domain}'

    def _om_ai_check_code(self, text):
        """ The customer typed a code while one is waiting.

        :return: None when the text is no code, else 'ok', 'wrong' or 'locked'
        """
        self.ensure_one()
        conversation = self.sudo()
        now = fields.Datetime.now()
        if not conversation.code_hash or not conversation.code_expiry or conversation.code_expiry < now:
            return None
        match = re.fullmatch(r'\s*(\d{3})[\s-]?(\d{3})\s*', text or '')
        if not match:
            return None
        partner = conversation._om_ai_customer()
        code = match.group(1) + match.group(2)
        if partner and hmac.compare_digest(conversation.code_hash, conversation._om_ai_hash_code(code)):
            conversation.write({'code_hash': False, 'code_expiry': False, 'code_tries': 0})
            partner._om_ai_whatsapp_set_verified(conversation.number, self.env._(
                'Verified on WhatsApp (%(number)s) with the code mailed to %(email)s.',
                number=conversation.number, email=partner.email))
            return 'ok'
        tries = conversation.code_tries + 1
        if tries >= CODE_TRIES:
            conversation.write({'code_hash': False, 'code_expiry': False, 'code_tries': 0,
                                'locked_until': now + timedelta(hours=LOCK_HOURS)})
            if partner:
                partner.message_post(body=self.env._(
                    'WhatsApp verification of %s locked for one hour after 3 wrong codes.', conversation.number))
            return 'locked'
        conversation.code_tries = tries
        return 'wrong'

    # ------------------------------------------------------------
    # ANSWERING
    # ------------------------------------------------------------

    def _om_ai_replies_today(self, account_wide=False):
        self.ensure_one()
        domain = [('state', '=', 'done'), ('replied', '=', True),
                  ('create_date', '>=', self.account_id._om_ai_today_start())]
        if account_wide:
            domain.append(('conversation_id.account_id', '=', self.account_id.id))
        else:
            domain.append(('conversation_id', '=', self.id))
        return self.env['om.ai.whatsapp.job'].sudo().search_count(domain)

    def _om_ai_handle(self, message):
        """ Answer the customer's ``message``. Return whether something was sent. """
        self.ensure_one()
        self._om_ai_sync_customer()
        return self.sudo().with_context(lang=self.sudo()._om_ai_lang())._om_ai_answer_message(message)

    def _om_ai_answer_message(self, message):
        self.ensure_one()
        conversation = self
        account = conversation.account_id
        conversation.last_message_date = fields.Datetime.now()
        text = html2plaintext(message.body or '').strip()
        words = normalise(text)
        if not account.om_ai_active:
            return False
        Blacklist = self.env['phone.blacklist'].sudo()
        if words in START_WORDS and (conversation.state == 'stopped' or conversation._om_ai_is_opted_out()):
            Blacklist._remove([conversation.number], message=self.env._('Opted in on WhatsApp'))
            conversation.state = 'ai'
            conversation._om_ai_send(self.env._("Welcome back! How can I help you?"))
            return True
        if words in STOP_WORDS and conversation.state != 'stopped':
            Blacklist._add([conversation.number], message=self.env._('Opted out on WhatsApp'))
            conversation.write({'state': 'stopped', 'pending_actions': False})
            conversation._om_ai_send(self.env._(
                "You will not get messages from us anymore. Send START to chat with us again."), force=True)
            conversation._om_ai_note(self.env._("The customer opted out (STOP)."))
            return True
        if conversation.state != 'ai' or conversation._om_ai_is_opted_out():
            return False
        if account._om_ai_in_working_hours():
            return False
        if any(re.search(r'\b%s\b' % re.escape(word), words) for word in account._om_ai_handover_words()):
            conversation._om_ai_hand_over(
                self.env._('the customer asked for a person'),
                message=self.env._("Sure, a colleague will answer you here shortly."))
            return True
        if (account.om_ai_daily_number_replies and
                conversation._om_ai_replies_today() >= account.om_ai_daily_number_replies) or \
                (account.om_ai_daily_replies and
                 conversation._om_ai_replies_today(account_wide=True) >= account.om_ai_daily_replies):
            conversation._om_ai_hand_over(
                self.env._('the daily limit of assistant replies is reached'),
                message=self.env._("Thank you! A colleague will continue with you here shortly."))
            return True
        notes = []
        code = conversation._om_ai_check_code(text)
        if code == 'wrong':
            left = CODE_TRIES - conversation.code_tries
            conversation._om_ai_send(self.env._(
                "This code is not correct. You can try %s more time(s).", left))
            return True
        if code == 'locked':
            conversation._om_ai_send(self.env._(
                "This code is not correct. For your security, verification is locked for one hour."))
            return True
        if code == 'ok':
            notes.append('The customer typed the right email code: they are verified now (level 2). Thank them '
                         'briefly and continue with what they asked before the code.')
        pending = conversation.pending_actions or []
        if pending:
            conversation.write({'pending_actions': False})
            fresh = conversation.pending_date and conversation.pending_date > fields.Datetime.now() - timedelta(
                hours=PENDING_HOURS)
            if fresh and is_yes(text):
                return conversation._om_ai_confirm(pending)
            notes.append('The customer did not confirm the action you proposed (%s): nothing was done. Answer '
                         'their new message.' % ', '.join(action['tool'] for action in pending))
        return conversation._om_ai_run(notes)

    def _om_ai_confirm(self, pending):
        """ The customer said yes: run the actions they confirmed. """
        self.ensure_one()
        env_self = self._om_ai_env()
        Engine = env_self.env['om.ai']
        results = []
        for action in pending:
            result = Engine._ai_confirm_action(action)
            results.append(result)
            _logger.info("WhatsApp assistant ran %s for %s: %s", action['tool'], self.number, result)
        errors = [result['error'] for result in results if isinstance(result, dict) and result.get('error')]
        if errors:
            return self._om_ai_run(['The customer said YES but the action failed: %s. Tell them and help.'
                                    % '; '.join(errors)])
        self.reply_count += 1
        return True

    def _om_ai_history(self):
        """ The last messages of the conversation, as the AI reads them. """
        self.ensure_one()
        channel = self.channel_id
        assistant = self.account_id._om_ai_get_user().partner_id
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
            ('message_type', 'in', ('om_social', 'comment')),
        ], order='id desc', limit=HISTORY_SIZE)
        history = []
        for message in reversed(messages):
            text = html2plaintext(message.body or '').strip()
            if message.attachment_ids:
                text = '\n'.join(filter(None, [text, '[%s]' % ', '.join(message.attachment_ids.mapped('name'))]))
            if not text:
                continue
            author = message.author_id
            if author == assistant:
                history.append({'role': 'assistant', 'content': text})
            elif author and author.user_ids and not author.partner_share:
                history.append({'role': 'assistant', 'content': '(%s, of our team) %s' % (author.name, text)})
            else:
                history.append({'role': 'user', 'content': text})
        while history and history[0]['role'] == 'assistant':
            history.pop(0)
        return history

    def _om_ai_context_text(self):
        """ What the assistant may know of the customer, for the prompt. """
        self.ensure_one()
        partner = self._om_ai_customer()
        level = self._om_ai_level()
        lines = []
        if partner:
            lines.append('Customer: %s (the contact in Odoo).' % partner.name)
        elif len(self._om_ai_number_partners()) > 1:
            lines.append('This number belongs to several contacts in Odoo: treat the customer as unknown. They '
                         'cannot order nor see documents here; offer a colleague for that (wa_hand_over).')
        else:
            lines.append('Unknown number: no contact in Odoo yet.')
        if self.profile_name:
            lines.append('WhatsApp profile name: %s.' % self.profile_name)
        lines.append({
            0: 'Level 0: answer general questions only (products, public prices, in stock or not, the knowledge '
               'text). Before the first item of an order, ask the name with the wa_set_customer_name tool.',
            1: 'Level 1: known customer. Their own quotations, payment links and order status are allowed. '
               'Invoices, balance and addresses need level 2: offer wa_send_verification_code.',
            2: 'Level 2: known customer. Their invoices, open balance and addresses are allowed too.',
        }[level])
        order = self.order_id
        if order and order.state in ('draft', 'sent'):
            lines.append('Current quotation: %s (%s, total %s %s).' % (
                order.name, dict(order._fields['state']._description_selection(self.env))[order.state],
                order.amount_total, order.currency_id.name))
        return '\n'.join(lines)

    def _om_ai_run(self, notes=None):
        """ Let the AI answer with the tools enabled on the account. """
        self.ensure_one()
        account = self.account_id
        env_self = self._om_ai_env()
        env = env_self.env
        prompt = env['om.ai.prompt'].sudo()._get_by_code('whatsapp_sales')
        messages = prompt.with_context(lang=env_self._om_ai_lang())._render({
            'company': account.company_id.name,
            'persona': account.om_ai_persona or '',
            'knowledge': account.om_ai_knowledge or '-',
            'date': fields.Date.context_today(env_self),
            'customer': self._om_ai_context_text(),
            'currency': account.company_id.currency_id.name,
        })
        messages = [message for message in messages if message['role'] == 'system']
        history = self._om_ai_history()
        if not history:
            return False
        messages += history
        for note in notes or []:
            messages.append({'role': 'system', 'content': note})
        tools = env['om.ai.tool']._get_available(codes=account.om_ai_tool_ids.mapped('code')) \
            if account.om_ai_tool_ids else env['om.ai.tool']
        try:
            result = env['om.ai']._ai_run_agent(messages, tools=tools, max_steps=8, feature='whatsapp')
            for _attempt in range(2):
                refused = env_self._om_ai_refuse_pending(result)
                if not refused:
                    break
                result = env['om.ai']._ai_run_agent(refused, tools=tools, max_steps=4, feature='whatsapp')
        except UserError as error:
            _logger.info("WhatsApp assistant could not answer %s: %s", self.number, error)
            self._om_ai_hand_over(
                self.env._('the AI could not answer: %s', error.args[0] if error.args else error),
                message=self.env._("Thank you for your message! A colleague will answer you here shortly."))
            return True
        self.invalidate_recordset()
        if self.state != 'ai':
            # a tool handed the conversation over and told the customer
            return True
        text = self._om_ai_whatsapp_style(result.get('text'))
        pending = result.get('pending_actions') or []
        if pending:
            self.write({'pending_actions': pending, 'pending_date': fields.Datetime.now()})
            summary = env_self._om_ai_pending_summary(pending)
            text = '\n\n'.join(filter(None, [text, summary]))
        if not text:
            return False
        self._om_ai_send(text)
        self.reply_count += 1
        return True

    def _om_ai_refuse_pending(self, result):
        """ The actions the AI proposed that could not run (level, missing
        address...) are not put to the customer: the AI gets the reason in
        their place and answers again. Return the conversation to go on
        with, or None when every action can be confirmed. """
        self.ensure_one()
        pending = result.get('pending_actions') or []
        if not pending:
            return None
        Tool = self.env['om.ai.tool']
        refusals = {}
        for action in pending:
            tool = Tool._get_available(codes=[action['tool']])
            refusal = tool._om_ai_check_pending(action.get('arguments')) if tool else {'error': 'Unknown tool.'}
            if refusal:
                refusals[action['tool_call_id']] = refusal
        if not refusals:
            return None
        messages = []
        for message in result['messages']:
            if message.get('role') == 'tool' and message.get('tool_call_id') in refusals:
                message = dict(message, content=json.dumps(refusals[message['tool_call_id']]))
            messages.append(message)
        while messages and messages[-1].get('role') == 'assistant' and not messages[-1].get('tool_calls'):
            messages.pop()
        return messages

    def _om_ai_pending_summary(self, pending):
        """ What the customer confirms, written by the code: the AI never
        writes the amounts the customer says yes to. """
        self.ensure_one()
        parts = []
        for action in pending:
            if action['tool'] == 'wa_send_quotation' and self.order_id:
                parts.append(self.order_id._om_ai_whatsapp_summary())
            else:
                parts.append(action.get('tool_name') or action['tool'])
        parts.append(self.env._("Reply YES to confirm."))
        return '\n\n'.join(parts)
