import json
import logging
import re
from datetime import timedelta

import psycopg2
from markupsafe import Markup

from odoo import SUPERUSER_ID, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import html2plaintext

from odoo.addons.om_ai.models.om_ai_chat_job import markdown_to_html

_logger = logging.getLogger(__name__)

HISTORY_SIZE = 20
MAX_STEPS = 4
MAX_PRODUCTS = 5
MAX_TOOL_CHARS = 6000
CURRENCY_MARKS = r'(?:\$|\u20ac|\u00a3|\u20b9|\u00a5|USD|EUR|GBP|INR|AED|SAR|CHF|CAD|AUD|JPY|Rs\.?)'
NUMBER = r'\d{1,3}(?:[ ,.\u00a0]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?'
AMOUNT_RE = re.compile(r'(?:%s)\s?(%s)|(%s)\s?(?:%s)' % (CURRENCY_MARKS, NUMBER, NUMBER, CURRENCY_MARKS))
ANY_NUMBER_RE = re.compile(r'\d+(?:[.,\u00a0 ]\d+)*')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _amount_value(text):
    """Number of a written amount: 1,299.00 / 1.299,00 / 1 299 / 49.9 -> float."""
    digits = re.sub(r'[\s\u00a0]', '', text)
    if re.search(r'[.,]\d{1,2}$', digits):
        whole, decimals = digits[:-3 if digits[-3] in '.,' else -2], digits[-2:].lstrip('.,')
        whole = re.sub(r'[.,]', '', whole)
        try:
            return round(float('%s.%s' % (whole or '0', decimals)), 2)
        except ValueError:
            return None
    try:
        return round(float(re.sub(r'[.,]', '', digits)), 2)
    except ValueError:
        return None


class OmAiLivechatJob(models.Model):
    """A visitor message waiting for the answer of the AI agent. Answers are
    computed by a triggered scheduled action: the visitor's request returns at once."""
    _name = 'om.ai.livechat.job'
    _description = 'AI Live Chat Answer'
    _order = 'id desc'

    channel_id = fields.Many2one('discuss.channel', string='Chat', required=True, ondelete='cascade', index=True)
    message_id = fields.Many2one('mail.message', string='Visitor Message', ondelete='cascade')
    question = fields.Text(compute='_compute_question')
    agent_id = fields.Many2one('om.ai.livechat.agent', string='Agent', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, ondelete='cascade')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Answered'),
        ('handover', 'Handed Over'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    ], default='pending', required=True, index=True)
    answer = fields.Text(readonly=True)
    sources = fields.Text(string='Knowledge Used', readonly=True)
    tool_log = fields.Text(string='Tools Used', readonly=True)
    error = fields.Text(readonly=True)

    def _compute_question(self):
        for job in self:
            job.question = html2plaintext(job.message_id.sudo().body or '').strip()

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------
    def _cron_process(self):
        jobs = self.search([('state', '=', 'pending')], order='id', limit=20)
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(jobs))
        for job in jobs:
            try:
                job.with_user(SUPERUSER_ID).with_company(job.company_id)._process()
            except psycopg2.errors.SerializationFailure:
                # the visitor wrote at the same time: answer in the next run, with the new message
                self.env.cr.rollback()
                break
            if not Cron._commit_progress(1):
                break
        if self.search_count([('state', '=', 'pending')], limit=1):
            self.env.ref('om_ai_livechat.ir_cron_om_ai_livechat')._trigger()
        else:
            self.search([('state', '!=', 'pending'),
                         ('create_date', '<', fields.Datetime.now() - timedelta(days=90))]).unlink()

    def _bot_member(self):
        return self.channel_id.sudo().channel_member_ids.filtered(lambda m: m.partner_id == self.agent_id.partner_id)

    def _process(self):
        self.ensure_one()
        channel = self.channel_id.sudo()
        bot_member = self._bot_member()
        if (not bot_member or channel.livechat_end_dt or channel.livechat_agent_history_ids
                or self.search_count([('channel_id', '=', channel.id), ('state', '=', 'pending'),
                                      ('id', '>', self.id)], limit=1)):
            # an operator took over, the chat ended, or a newer message will be answered with this one
            self.state = 'skipped'
            return
        agent = self.agent_id.sudo().with_context(lang=channel.livechat_lang_id.code or self.env.lang)
        # the chat is updated by the messages posted below (its last interest date, in a separate transaction
        # that skips locked chats): lock it first so that both never write it at the same time
        self.env.cr.execute('SELECT id FROM discuss_channel WHERE id = %s FOR NO KEY UPDATE', [channel.id])
        try:
            with self.env.cr.savepoint():
                self._answer(agent)
        except (UserError, AccessError) as error:
            message = str(error.args[0] if error.args else error)
            _logger.info('AI live chat agent could not answer: %s', message)
            self.write({'state': 'failed', 'error': message})
            # the AI is down or a limit is reached: a person takes over, or the visitor is told
            self._handover(agent, reason=self.env._('The AI could not answer.'))
        except Exception as error:  # noqa: BLE001 - the visitor always gets an answer
            _logger.exception('AI live chat agent failed')
            self.write({'state': 'failed', 'error': repr(error)})
            self._handover(agent, reason=self.env._('The AI could not answer.'))
        finally:
            bot_member.exists()._notify_typing(False)

    # ------------------------------------------------------------------
    # Answer
    # ------------------------------------------------------------------
    def _post(self, agent, text):
        body = markdown_to_html(text) or Markup('<p>%s</p>') % text
        return self.channel_id.sudo().with_context(mail_post_autofollow_author_skip=True).message_post(
            author_id=agent.partner_id.id,
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    def _history(self, agent):
        channel = self.channel_id.sudo()
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('message_type', '=', 'comment'),
            ('id', '<=', self.message_id.id),
        ], order='id desc', limit=HISTORY_SIZE)
        visitor = channel.livechat_customer_history_ids
        conversation = []
        for message in reversed(messages):
            text = html2plaintext(message.body or '').strip()
            if not text:
                continue
            if message.author_id == agent.partner_id:
                conversation.append({'role': 'assistant', 'content': text})
            elif (message.author_guest_id and message.author_guest_id in visitor.guest_id) or (
                    message.author_id and message.author_id in visitor.partner_id):
                conversation.append({'role': 'user', 'content': text[:agent.max_message_chars or 1000]})
        while conversation and conversation[0]['role'] == 'assistant':
            conversation.pop(0)
        return conversation

    def _knowledge(self, agent, question, context=''):
        """The parts of the knowledge closest to the question, completed with parts about the recent
        messages of the visitor."""
        Chunk = self.env['om.ai.livechat.chunk'].sudo()
        sources = agent.source_ids.filtered('active')
        limit = agent.knowledge_count or 5
        chunks = Chunk.browse()
        for text in filter(None, [question, context]):
            if len(chunks) >= limit:
                break
            found = Chunk.browse()
            if agent.use_embeddings:
                try:
                    found = Chunk._search_embedding(sources, text, limit=limit)
                except UserError as error:
                    _logger.info('Live chat knowledge search by meaning failed: %s', error)
            if not found:
                found = Chunk._search_text(sources, text, limit=limit)
            chunks |= found
        return chunks[:limit]

    def _tools(self, agent):
        tools = []
        if agent.tool_products and 'product.template' in self.env:
            tools.append({
                'name': 'search_products',
                'description': 'Search the products for sale by name or code. Returns their current price, '
                               'currency and availability. Always use it for prices and stock.',
                'parameters': {'type': 'object', 'properties': {
                    'query': {'type': 'string', 'description': 'Product name, words of it or its code'},
                }, 'required': ['query']},
            })
        if agent.tool_lead and 'crm.lead' in self.env:
            tools.append({
                'name': 'create_lead',
                'description': 'Create a sales lead when the visitor wants a quote, a call back or to buy, '
                               'once they gave an email or a phone number.',
                'parameters': {'type': 'object', 'properties': {
                    'contact_name': {'type': 'string'},
                    'email': {'type': 'string'},
                    'phone': {'type': 'string'},
                    'company_name': {'type': 'string'},
                    'subject': {'type': 'string', 'description': 'Short title of the request'},
                    'details': {'type': 'string', 'description': 'What the visitor wants'},
                }, 'required': ['subject']},
            })
        if agent.tool_ticket and 'om.helpdesk.ticket' in self.env:
            tools.append({
                'name': 'create_ticket',
                'description': 'Create a support ticket for a problem the visitor reports, once they gave an '
                               'email address.',
                'parameters': {'type': 'object', 'properties': {
                    'contact_name': {'type': 'string'},
                    'email': {'type': 'string'},
                    'subject': {'type': 'string', 'description': 'Short title of the problem'},
                    'description': {'type': 'string', 'description': 'The problem in the words of the visitor'},
                }, 'required': ['subject', 'email']},
            })
        tools.append({
            'name': 'handover_to_operator',
            'description': 'Pass the chat to a human colleague: when the visitor asks for a person'
                           + (', or when the knowledge and the tools do not answer the question.'
                              if agent.handover_uncertain else '.'),
            'parameters': {'type': 'object', 'properties': {
                'reason': {'type': 'string'},
            }, 'required': []},
        })
        return tools

    def _system_prompt(self, agent, chunks, tools):
        knowledge = '\n\n'.join('[%s] %s\n%s' % (index, chunk.name or chunk.source_id.name, chunk.content)
                                for index, chunk in enumerate(chunks, start=1)) or self.env._('(nothing found)')
        prompt = self.env['om.ai.prompt'].sudo().with_company(agent.company_id)._get_by_code('livechat_agent')
        messages = prompt._render({
            'agent': agent.name,
            'company': agent.company_id.name,
            'date': fields.Date.context_today(self),
            'instructions': agent.instructions or '',
            'knowledge': knowledge,
            'tools': ', '.join(tool['name'] for tool in tools),
        })
        return [message for message in messages if message['role'] == 'system']

    def _answer(self, agent):
        channel = self.channel_id.sudo()
        question = self.question[:agent.max_message_chars or 1000]
        # limits
        replies = self.search_count([('channel_id', '=', channel.id), ('state', '=', 'done')])
        if agent.max_replies and replies >= agent.max_replies:
            self.write({'state': 'handover', 'error': self.env._('Answer limit of the chat reached.')})
            self._handover(agent, reason=self.env._('Answer limit of the chat reached.'))
            return
        if agent.max_messages_hour and agent._visitor_messages_last_hour(self.message_id) > agent.max_messages_hour:
            already = self.search_count([('channel_id', '=', channel.id), ('id', '<', self.id),
                                         ('error', '=', 'rate limit')], limit=1)
            self.write({'state': 'skipped', 'error': 'rate limit'})
            if not already:
                self._post(agent, self.env._('You are sending many messages. Please wait a moment before '
                                             'writing again.'))
            return
        lowered = question.lower()
        if any(re.search(r'\b%s\b' % re.escape(word), lowered) for word in agent._keywords()):
            self.write({'state': 'handover', 'error': False})
            self._handover(agent, reason=self.env._('The visitor asked for a person.'))
            return

        conversation = self._history(agent)
        if not conversation:
            self.state = 'skipped'
            return
        recent = ' '.join(m['content'] for m in conversation[-4:-1] if m['role'] == 'user')
        chunks = self._knowledge(agent, question, recent)
        tools = self._tools(agent)
        messages = self._system_prompt(agent, chunks, tools) + conversation
        engine = self.env['om.ai'].sudo().with_company(agent.company_id)
        tool_outputs, tool_log, text = [], [], ''
        for step in range(MAX_STEPS + 1):
            last = step == MAX_STEPS
            result = engine._ai_chat(messages, purpose=agent.purpose, model=agent.ai_model_id or None,
                                     tools=None if last else tools, feature='livechat', max_tokens=800)
            text = (result.get('text') or '').strip()
            if not result.get('tool_calls') or last:
                break
            messages.append({'role': 'assistant', 'content': text, 'tool_calls': result['tool_calls']})
            for call in result['tool_calls']:
                name, arguments = call['name'], call.get('arguments') or {}
                if name == 'handover_to_operator':
                    tool_log.append('handover_to_operator %s' % json.dumps(arguments, ensure_ascii=False))
                    self.write({'state': 'handover', 'tool_log': '\n'.join(tool_log),
                                'sources': self._sources_text(chunks)})
                    self._handover(agent, reason=arguments.get('reason') or self.env._('Asked by the AI.'))
                    return
                output = self._run_tool(agent, name, arguments)
                tool_outputs.append(output)
                tool_log.append('%s %s -> %s' % (name, json.dumps(arguments, ensure_ascii=False),
                                                 json.dumps(output, ensure_ascii=False, default=str)[:500]))
                messages.append({
                    'role': 'tool', 'tool_call_id': call['id'], 'name': name,
                    'content': json.dumps(output, ensure_ascii=False, default=str)[:MAX_TOOL_CHARS],
                })
        if not text:
            text = self.env._('Sorry, I have no answer to that. Can I help you with something else?')
        unknown = self._unknown_amounts(text, chunks, tool_outputs)
        if unknown:
            # an amount that neither the knowledge nor the tools gave: never send an invented price
            tool_log.append('price check: %s not found in the knowledge or the tools' % ', '.join(unknown))
            text = self.env._('I cannot confirm that price here. Let me check with a colleague.')
            self._post(agent, text)
            self.write({'state': 'handover', 'answer': text, 'tool_log': '\n'.join(tool_log),
                        'sources': self._sources_text(chunks)})
            self._handover(agent, reason=self.env._('Price not confirmed.'), silent_intro=True)
            return
        self._post(agent, text)
        self.write({'state': 'done', 'answer': text, 'tool_log': '\n'.join(tool_log) or False,
                    'sources': self._sources_text(chunks)})

    @staticmethod
    def _sources_text(chunks):
        return '\n'.join('[%s] %s: %s' % (index, chunk.source_id.name, chunk.name or '')
                         for index, chunk in enumerate(chunks, start=1)) or False

    @staticmethod
    def _unknown_amounts(text, chunks, tool_outputs):
        """Amounts with a currency in ``text`` that are not in the knowledge or the tool results."""
        known_text = '\n'.join(chunks.mapped('content')) + '\n' + json.dumps(tool_outputs, default=str)
        known = {value for value in (_amount_value(match) for match in ANY_NUMBER_RE.findall(known_text))
                 if value is not None}
        unknown = []
        for match in AMOUNT_RE.finditer(text):
            written = match.group(1) or match.group(2)
            value = _amount_value(written)
            if value is not None and value not in known:
                unknown.append(match.group(0).strip())
        return unknown

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    def _run_tool(self, agent, name, arguments):
        method = {
            'search_products': self._tool_search_products,
            'create_lead': self._tool_create_lead,
            'create_ticket': self._tool_create_ticket,
        }.get(name)
        if not method or name not in [tool['name'] for tool in self._tools(agent)]:
            return {'error': 'Unknown tool %s.' % name}
        try:
            with self.env.cr.savepoint():
                return method(agent, **{key: value for key, value in arguments.items() if isinstance(key, str)})
        except (UserError, AccessError, ValueError, TypeError) as error:
            return {'error': str(error.args[0] if error.args else error)}

    def _tool_search_products(self, agent, query='', **kwargs):
        Product = self.env['product.template'].sudo().with_company(agent.company_id)
        domain = Domain('sale_ok', '=', True) & Domain('company_id', 'in', [agent.company_id.id, False])
        if 'is_published' in Product._fields:
            domain &= Domain('is_published', '=', True)
        query = (query or '').strip()[:100]
        if not query:
            return {'error': 'Give a product name.'}
        products = Product.search(domain & (Domain('name', 'ilike', query) | Domain('default_code', '=ilike', query)),
                                  limit=MAX_PRODUCTS)
        if not products:
            words = [word for word in re.findall(r'\w{3,}', query)][:5]
            if words:
                products = Product.search(domain & Domain.OR(Domain('name', 'ilike', word) for word in words),
                                          limit=MAX_PRODUCTS)
        currency = agent.company_id.currency_id
        result = []
        for product in products:
            item = {
                'name': product.name,
                'code': product.default_code or '',
                'price': round(product.list_price, currency.decimal_places),
                'currency': product.currency_id.name or currency.name,
                'price_text': (product.currency_id or currency).format(product.list_price).replace(
                    '\u00a0', ' '),
            }
            if 'website_url' in product._fields and product.website_url:
                item['url'] = product.get_base_url() + product.website_url
            if 'is_storable' in product._fields and product.is_storable:
                quantity = product.qty_available
                item['availability'] = 'in stock' if quantity > 0 else 'out of stock'
                if agent.show_stock_quantity:
                    item['quantity_in_stock'] = quantity
            result.append(item)
        if not result:
            return {'products': [], 'note': 'No product matches. Do not give any price.'}
        return {'products': result, 'note': 'Prices are the current list prices, taxes as on the website.'}

    def _visitor_partner(self):
        channel = self.channel_id.sudo()
        return channel.livechat_customer_history_ids.partner_id[:1]

    def _transcript(self):
        lines = []
        for message in self.env['mail.message'].sudo().search([
                ('model', '=', 'discuss.channel'), ('res_id', '=', self.channel_id.id),
                ('message_type', '=', 'comment')], order='id', limit=50):
            author = message.author_id.name or message.author_guest_id.name or ''
            lines.append(Markup('<li><b>%s</b>: %s</li>') % (author, html2plaintext(message.body or '').strip()))
        return Markup('<ul>%s</ul>') % Markup('').join(lines)

    def _tool_create_lead(self, agent, subject='', contact_name='', email='', phone='', company_name='', details='',
                          **kwargs):
        if not email and not phone:
            return {'error': 'Ask the visitor for an email address or a phone number first.'}
        if email and not EMAIL_RE.match(email.strip()):
            return {'error': 'The email address does not look valid. Ask the visitor again.'}
        Lead = self.env['crm.lead'].sudo().with_company(agent.company_id)
        partner = self._visitor_partner()
        vals = {
            'name': (subject or self.env._('Live chat request'))[:200],
            'contact_name': contact_name or False,
            'email_from': email or False,
            'phone': phone or False,
            'partner_name': company_name or False,
            'description': Markup('<p>%s</p>%s') % (details or '', self._transcript()),
            'company_id': agent.company_id.id,
            'type': 'lead' if self._use_leads() else 'opportunity',
        }
        if partner:
            vals['partner_id'] = partner.id
        if 'origin_channel_id' in Lead._fields:
            vals['origin_channel_id'] = self.channel_id.id
        lead = Lead.create(vals)
        return {'created': True, 'reference': lead.id,
                'note': 'Tell the visitor the team will contact them. Do not promise a delay or a price.'}

    def _use_leads(self):
        group = self.env.ref('crm.group_use_lead', raise_if_not_found=False)
        return bool(group) and group in self.env.ref('base.group_user').all_implied_ids

    def _tool_create_ticket(self, agent, subject='', email='', contact_name='', description='', **kwargs):
        if not email or not EMAIL_RE.match(email.strip()):
            return {'error': 'Ask the visitor for a valid email address first.'}
        Ticket = self.env['om.helpdesk.ticket'].sudo().with_company(agent.company_id)
        vals = {
            'name': (subject or self.env._('Live chat problem'))[:200],
            'email_from': email,
            'partner_name': contact_name or False,
            'description': Markup('<p>%s</p>%s') % (description or '', self._transcript()),
            'company_id': agent.company_id.id,
        }
        partner = self._visitor_partner()
        if partner:
            vals['partner_id'] = partner.id
        ticket = Ticket.create(vals)
        return {'created': True, 'ticket_number': ticket.number if 'number' in ticket._fields else ticket.id,
                'note': 'Give the ticket number to the visitor.'}

    # ------------------------------------------------------------------
    # Hand-over
    # ------------------------------------------------------------------
    def _add_error(self, text):
        self.error = '\n'.join(filter(None, [self.error, text]))

    def _handover(self, agent, reason='', silent_intro=False):
        """Pass the chat to an available operator, or tell the visitor nobody is available."""
        channel = self.channel_id.sudo()
        operator = self.env['res.users']
        if channel.livechat_channel_id and agent._within_hours():
            operator = channel.livechat_channel_id._get_operator(
                lang=channel.livechat_lang_id.code, country_id=channel.country_id.id)
        if operator and operator != self.env.user:
            if not silent_intro:
                self._post(agent, self.env._('I am passing you to %s, one moment please.',
                                             operator.livechat_username or operator.name))
            visitor = channel.livechat_customer_history_ids[:1]
            channel._forward_human_operator(users=operator)
            channel.write({
                'om_ai_handed_over': True,
                'name': ' '.join(filter(None, [visitor.partner_id.name or visitor.guest_id.name,
                                               operator.livechat_username or operator.name])),
            })
            self._add_error(self.env._('Handed over to %(operator)s: %(reason)s', operator=operator.name,
                                       reason=reason))
            return operator
        channel.livechat_failure = 'no_agent'
        self._add_error(self.env._('No operator available: %s', reason))
        self._post(agent, agent.no_operator_message or self.env._('No colleague is available right now.'))
        return operator
