import html
import logging
import re
from datetime import timedelta

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

HISTORY_SIZE = 20


def markdown_to_html(text):
    """Small markdown subset (paragraphs, lists, headings, bold, italic, code,
    links) to safe HTML for Discuss messages. Everything is escaped first."""

    def inline(value):
        value = html.escape(value, quote=False)
        value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
        value = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', value)
        value = re.sub(r'(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])', r'<i>\1</i>', value)
        value = re.sub(r'\[([^\]]+)\]\((https?://[^\s)"]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', value)
        return value

    parts, list_tag, code = [], None, None
    for line in (text or '').replace('\r\n', '\n').split('\n'):
        if code is not None:
            if line.strip().startswith('```'):
                parts.append('<pre>%s</pre>' % html.escape('\n'.join(code), quote=False))
                code = None
            else:
                code.append(line)
            continue
        stripped = line.strip()
        bullet = re.match(r'^[-*+]\s+(.*)', stripped)
        number = re.match(r'^\d+[.)]\s+(.*)', stripped)
        tag = 'ul' if bullet else 'ol' if number else None
        if list_tag and tag != list_tag:
            parts.append('</%s>' % list_tag)
            list_tag = None
        if stripped.startswith('```'):
            code = []
        elif tag:
            if not list_tag:
                parts.append('<%s>' % tag)
                list_tag = tag
            parts.append('<li>%s</li>' % inline((bullet or number).group(1)))
        elif re.match(r'^#{1,6}\s', stripped):
            parts.append('<p><b>%s</b></p>' % inline(stripped.lstrip('#').strip()))
        elif stripped:
            parts.append('<p>%s</p>' % inline(stripped))
    if code is not None:
        parts.append('<pre>%s</pre>' % html.escape('\n'.join(code), quote=False))
    if list_tag:
        parts.append('</%s>' % list_tag)
    return Markup(''.join(parts))  # noqa: S704 - built from escaped text only


class OmAiChatJob(models.Model):
    """A message waiting for an answer of the AI Assistant in Discuss. Answers
    are computed by a cron so posting a message never waits for the AI."""
    _name = 'om.ai.chat.job'
    _description = 'AI Assistant Message'
    _order = 'id'

    channel_id = fields.Many2one('discuss.channel', required=True, ondelete='cascade', index=True)
    message_id = fields.Many2one('mail.message', ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed')],
                             default='pending', required=True, index=True)
    error = fields.Text()

    def _cron_process(self):
        jobs = self.search([('state', '=', 'pending')], limit=20)
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(jobs))
        for job in jobs:
            job._process()
            if not Cron._commit_progress(1):
                break
        if self.search_count([('state', '=', 'pending')], limit=1):
            self.env.ref('om_ai.ir_cron_om_ai_chat')._trigger()
        else:
            self.search([('state', '!=', 'pending'),
                         ('create_date', '<', fields.Datetime.now() - timedelta(days=7))]).unlink()

    def _process(self):
        self.ensure_one()
        partner = self.env.ref('om_ai.partner_ai_assistant')
        member = self.channel_id.channel_member_ids.filtered(lambda m: m.partner_id == partner)
        user = self.user_id
        env_user = self.with_user(user).with_context(
            allowed_company_ids=(self.company_id | user.company_ids).ids,
            lang=user.lang, tz=user.tz,
        ).with_company(self.company_id)
        try:
            with self.env.cr.savepoint():
                answer = env_user._answer()
            body = markdown_to_html(answer) or Markup('<p>%s</p>') % self.env._('(no answer)')
            self.state = 'done'
        except (UserError, AccessError) as error:
            body = Markup('<p><i>%s</i></p>') % (error.args[0] if error.args else str(error))
            self.write({'state': 'failed', 'error': str(error.args[0] if error.args else error)})
        except Exception as error:  # noqa: BLE001 - always answer the user
            _logger.exception('AI Assistant failed')
            body = Markup('<p><i>%s</i></p>') % self.env._('Sorry, something went wrong. Please try again later.')
            self.write({'state': 'failed', 'error': repr(error)})
        member._notify_typing(False)
        self.channel_id.sudo().message_post(
            author_id=partner.id,
            body=body,
            message_type='comment',
            silent=True,
            subtype_xmlid='mail.mt_comment',
        )

    def _answer(self):
        """Run as the user who asked: build the conversation and let the AI answer."""
        self.ensure_one()
        partner = self.env.ref('om_ai.partner_ai_assistant')
        channel = self.channel_id
        domain = [('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('message_type', '=', 'comment')]
        if self.message_id:
            domain.append(('id', '<=', self.message_id.id))
        history = self.env['mail.message'].search(domain, order='id desc', limit=HISTORY_SIZE)
        prompt = self.env['om.ai.prompt']._get_by_code('discuss_assistant')
        messages = prompt._render({
            'user': self.env.user.name,
            'company': self.env.company.name,
            'date': fields.Date.context_today(self),
            'lang': self.env.user.lang,
        })
        messages = [msg for msg in messages if msg['role'] == 'system']
        group = channel.channel_type != 'chat'
        for message in reversed(history):
            text = html2plaintext(message.body or '').strip()
            if not text:
                continue
            if message.author_id == partner:
                messages.append({'role': 'assistant', 'content': text})
            else:
                messages.append({'role': 'user',
                                 'content': '%s: %s' % (message.author_id.name, text) if group else text})
        while messages and messages[-1]['role'] == 'assistant':
            messages.pop()
        if not any(msg['role'] == 'user' for msg in messages):
            raise UserError(self.env._('There is no question to answer.'))
        company = self.env.company.sudo()
        tools = self.env['om.ai.tool']._get_available(read_only=True) if company.om_ai_assistant_tools \
            else self.env['om.ai.tool']
        result = self.env['om.ai']._ai_run_agent(messages, tools=tools, max_steps=6, feature='discuss')
        return result['text']
