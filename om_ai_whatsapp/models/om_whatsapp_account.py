from datetime import datetime, timedelta, timezone

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

DEFAULT_PERSONA = """You are the friendly sales assistant of our shop on WhatsApp.
Keep answers short, like a chat message. Recommend products that fit what the customer asks for."""
DEFAULT_HANDOVER = 'human, person, agent, operator, salesperson, talk to someone'


class OmWhatsappAccount(models.Model):
    _inherit = 'om.whatsapp.account'

    om_ai_active = fields.Boolean(
        'AI Assistant',
        help="An AI assistant answers the customers who write to this number: products, prices, stock, "
             "quotations with an online payment link, order status and invoices.")
    om_ai_user_id = fields.Many2one(
        'res.users', string='Assistant User', readonly=True, copy=False,
        help="The WhatsApp Assistant user of the company: the assistant works with its rights, which only let it "
             "read products and the documents of the customer, and make draft quotations.")
    om_ai_persona = fields.Text(
        'Persona and Instructions', default=DEFAULT_PERSONA,
        help="How the assistant speaks and what it should do or avoid, in your own words.")
    om_ai_knowledge = fields.Text(
        'Knowledge',
        help="Opening hours, delivery areas and times, return policy, payment methods... The assistant answers "
             "general questions from this text only.")
    om_ai_tool_ids = fields.Many2many(
        'om.ai.tool', string='Enabled Tools', domain=[('om_ai_whatsapp', '=', True)],
        default=lambda self: self.env['om.ai.tool'].sudo().search([('om_ai_whatsapp', '=', True)]),
        help="What the assistant may do. The level each tool needs is enforced whatever the AI asks.")
    om_ai_salesperson_id = fields.Many2one(
        'res.users', string='Default Salesperson', domain=[('share', '=', False)],
        help="Salesperson of the quotations of customers who have none, and who takes over the conversations "
             "of those customers.")
    om_ai_carrier_ids = fields.Many2many(
        'delivery.carrier', string='Delivery Methods',
        help="Delivery methods the assistant offers. Empty: no delivery is added to the quotations.")
    om_ai_reminder_hours = fields.Integer(
        'Payment Reminder After (hours)', default=24,
        help="One reminder with the payment link when a quotation is still unpaid this long after the link was "
             "sent. 0: no reminder.")
    om_ai_hours_mode = fields.Selection([
        ('always', 'Always'),
        ('outside', 'Only Outside Working Hours'),
    ], string='Assistant Answers', default='always', required=True)
    om_ai_calendar_id = fields.Many2one(
        'resource.calendar', string='Working Hours',
        default=lambda self: self.env.company.resource_calendar_id,
        help="During these hours your team answers; the assistant only answers outside them.")
    om_ai_handover_keywords = fields.Char(
        'Hand-over Words', default=DEFAULT_HANDOVER,
        help="Comma-separated words: a customer message with one of them goes to a person at once.")
    om_ai_daily_replies = fields.Integer(
        'Replies per Day', default=500,
        help="Most answers of the assistant per day for this number. Beyond, the conversations go to a person. "
             "0: no limit.")
    om_ai_daily_number_replies = fields.Integer(
        'Replies per Customer per Day', default=40,
        help="Most answers of the assistant per day to one customer. Beyond, the conversation goes to a person. "
             "0: no limit.")
    om_ai_email_code = fields.Boolean(
        'Email Code for Private Data',
        help="Invoices, balance, addresses and company documents are shown only after the customer types a code "
             "sent to the email on their contact. Unchecked, they are shown to a number that is on exactly one "
             "contact.")
    om_ai_verify_days = fields.Integer(
        'Verification Valid (days)', default=30,
        help="How long a number stays verified after the customer typed the code sent to their email.")
    om_ai_document_scope = fields.Selection([
        ('own', 'Own Documents'),
        ('commercial', 'Documents of the Whole Company'),
    ], string='Private Data Covers', default='own', required=True,
        help="Own: the contact sees their own invoices and orders. Whole company: also those of the "
             "company they belong to and its other contacts.")
    om_ai_conversation_count = fields.Integer(compute='_compute_om_ai_conversation_count')

    def _compute_om_ai_conversation_count(self):
        counts = dict(self.env['om.ai.whatsapp.conversation']._read_group(
            [('account_id', 'in', self.ids)], ['account_id'], ['__count']))
        for account in self:
            account.om_ai_conversation_count = counts.get(account, 0)

    @api.model_create_multi
    def create(self, vals_list):
        accounts = super().create(vals_list)
        accounts.filtered('om_ai_active')._om_ai_ensure_user()
        return accounts

    def write(self, vals):
        res = super().write(vals)
        if vals.get('om_ai_active') or 'company_id' in vals:
            self.filtered('om_ai_active')._om_ai_ensure_user()
        return res

    def _om_ai_ensure_user(self):
        """ The WhatsApp Assistant user of the company of each account, made
        on first use: no password, so nobody can log in with it. """
        Users = self.env['res.users'].sudo().with_context(no_reset_password=True, mail_create_nosubscribe=True)
        group = self.env.ref('om_ai_whatsapp.group_om_ai_whatsapp_assistant')
        for account in self:
            company = account.company_id
            user = account.om_ai_user_id
            if not user or user.company_id != company:
                user = Users.with_context(active_test=False).search(
                    [('om_ai_whatsapp_assistant', '=', True), ('company_id', '=', company.id)], limit=1)
            if not user:
                user = Users.create({
                    'name': self.env._('WhatsApp Assistant'),
                    'login': f'om-ai-whatsapp-{company.id}',
                    'company_id': company.id,
                    'company_ids': [Command.set(company.ids)],
                    'om_ai_whatsapp_assistant': True,
                    'group_ids': [Command.set(group.ids)],
                    'image_1920': self.env.ref('om_ai.partner_ai_assistant').image_1920,
                    'notification_type': 'inbox',
                })
            elif not user.active:
                user.active = True
            account.sudo().om_ai_user_id = user

    def _om_ai_get_user(self):
        self.ensure_one()
        if not self.om_ai_user_id.active:
            self._om_ai_ensure_user()
        return self.om_ai_user_id.sudo()

    def _om_ai_in_working_hours(self, now=None):
        """ Whether the team is at work now, by the working hours of the account. """
        self.ensure_one()
        calendar = self.om_ai_calendar_id
        if self.om_ai_hours_mode != 'outside' or not calendar:
            return False
        now = (now or fields.Datetime.now()).replace(tzinfo=timezone.utc)
        intervals = calendar.sudo()._work_intervals_batch(now - timedelta(minutes=1), now + timedelta(minutes=1))
        return any(start <= now <= stop for start, stop, _meta in intervals.get(False, []))

    def _om_ai_handover_words(self):
        self.ensure_one()
        return [word.strip().lower() for word in (self.om_ai_handover_keywords or '').split(',') if word.strip()]

    def action_om_ai_conversations(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_ai_whatsapp.om_ai_whatsapp_conversation_action')
        action['domain'] = [('account_id', '=', self.id)]
        return action

    def action_om_ai_check(self):
        """ Tell the administrator what still keeps the assistant from answering. """
        self.ensure_one()
        problems = []
        if not self.can_send_unattended and not self._om_ai_browser_user():
            problems.append(self.env._(
                "The provider of this account cannot send by itself: the answers wait until a user sends them "
                "again, unless WhatsApp Web is open in the browser of a user."))
        try:
            self.env['om.ai'].with_company(self.company_id)._ai_get_model('chat')
        except UserError as error:
            problems.append(error.args[0])
        if not self.om_ai_tool_ids:
            problems.append(self.env._("No tool is enabled: the assistant can only chat."))
        message = '\n'.join(problems) or self.env._("The assistant is ready to answer.")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'warning' if problems else 'success', 'message': message, 'sticky': bool(problems)},
        }

    # ------------------------------------------------------------
    # RECEIVING: every provider ends here
    # ------------------------------------------------------------

    def _om_whatsapp_receive(self, number, body='', whatsapp_id=False, attachments=None, quoted_id=False,
                             from_me=False, profile_name=False, voice=False):
        message = super()._om_whatsapp_receive(
            number, body=body, whatsapp_id=whatsapp_id, attachments=attachments, quoted_id=quoted_id,
            from_me=from_me, profile_name=profile_name, voice=voice)
        if message and not from_me and self.om_ai_active and message.model == 'discuss.channel':
            self._om_ai_queue(message)
        return message

    def _om_ai_queue(self, message):
        """ The webhook never waits for the AI: a job answers in the background. """
        self.ensure_one()
        Job = self.env['om.ai.whatsapp.job'].sudo()
        if Job.search_count([('message_id', '=', message.id)], limit=1):
            return
        channel = self.env['discuss.channel'].sudo().browse(message.res_id)
        conversation = self.env['om.ai.whatsapp.conversation'].sudo()._om_ai_get(channel)
        Job.create({'conversation_id': conversation.id, 'message_id': message.id})
        self.env.ref('om_ai_whatsapp.ir_cron_om_ai_whatsapp_jobs').sudo()._trigger()

    # ------------------------------------------------------------
    # SENDING without a user at the screen
    # ------------------------------------------------------------

    def _om_ai_browser_user(self):
        """ A provider that sends through the browser of a user (WhatsApp Web)
        sends the answers of the assistant through the user who had it open in
        the last minutes. """
        self.ensure_one()
        if 'om_whatsapp_web_seen_user_id' not in self._fields or self.provider != 'web':
            return self.env['res.users']
        seen = self.om_whatsapp_web_seen
        if not seen or seen < fields.Datetime.now() - timedelta(minutes=10):
            return self.env['res.users']
        return self.om_whatsapp_web_seen_user_id

    def _om_ai_deliver(self, notifications):
        """ Send the messages of the assistant. """
        self.ensure_one()
        if self.can_send_unattended:
            return self._om_whatsapp_send_automated(notifications)
        user = self._om_ai_browser_user()
        if user and len(notifications) == 1:
            action = self._om_whatsapp_send(notifications)
            if action:
                user._bus_send('om_whatsapp/action', {'action': action})
            return None
        return self._om_whatsapp_send_automated(notifications)

    @staticmethod
    def _om_ai_today_start():
        return datetime.combine(fields.Date.today(), datetime.min.time())
