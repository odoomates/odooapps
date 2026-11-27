import base64
from datetime import timedelta

import pytz

from odoo import api, fields, models
from odoo.tools.misc import file_open

DEFAULT_KEYWORDS = 'human, operator, person, agent, someone real, talk to someone'


class OmAiLivechatAgent(models.Model):
    """An AI agent that answers the visitors of live chat channels."""
    _name = 'om.ai.livechat.agent'
    _description = 'AI Live Chat Agent'
    _order = 'sequence, id'

    name = fields.Char(required=True, help='The name the visitors see.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner', string='Chat Contact', readonly=True, copy=False,
                                 ondelete='restrict', help='The contact the messages of the agent are posted as.')
    image_1920 = fields.Image(related='partner_id.image_1920', readonly=False)
    channel_ids = fields.One2many('im_livechat.channel', 'om_ai_agent_id', string='Live Chat Channels')
    # the answers
    instructions = fields.Text(
        translate=True,
        default='Be friendly and brief: two or three sentences. Answer in the language of the visitor.',
        help='Your rules for the agent: tone, what to talk about, what to avoid.')
    purpose = fields.Selection([('chat', 'Chat'), ('fast', 'Fast')], default='chat', required=True,
                               help='Which default AI model of the company answers.')
    ai_model_id = fields.Many2one('om.ai.model', string='AI Model', domain=[('cap_chat', '=', True)],
                                  help='Use this model instead of the company default for the purpose.')
    source_ids = fields.Many2many('om.ai.livechat.source', 'om_ai_livechat_agent_source_rel', 'agent_id',
                                  'source_id', string='Knowledge Sources')
    use_embeddings = fields.Boolean(
        string='Search by Meaning',
        help='Find the knowledge with the embeddings model of the company instead of the words of the question. '
             'Needs an embeddings model in the AI settings.')
    knowledge_count = fields.Integer(string='Parts Given per Answer', default=5)
    # tools
    tool_products = fields.Boolean(string='Look Up Products', default=True,
                                   help='Search the products with their live price and stock.')
    show_stock_quantity = fields.Boolean(string='Tell Stock Quantities',
                                         help='Give the quantity in stock, not only whether the product is in stock.')
    tool_lead = fields.Boolean(string='Create Leads', default=True,
                               help='Create a lead in CRM with the contact details the visitor gives.')
    tool_ticket = fields.Boolean(string='Create Helpdesk Tickets', default=True,
                                 help='Create a helpdesk ticket for a problem the visitor reports.')
    has_crm = fields.Boolean(compute='_compute_installed_apps')
    has_helpdesk = fields.Boolean(compute='_compute_installed_apps')
    has_products = fields.Boolean(compute='_compute_installed_apps')
    # hand-over
    handover_keywords = fields.Char(
        string='Hand-over Words', default=DEFAULT_KEYWORDS, translate=True,
        help='Comma-separated words: a visitor writing one of them is handed over to an operator at once.')
    handover_uncertain = fields.Boolean(string='Hand Over When Not Sure', default=True,
                                        help='The agent hands over when the knowledge and the tools do not answer.')
    handover_hours = fields.Boolean(string='Operator Hours',
                                    help='Hand over only within these hours (time zone of the agent).')
    handover_hour_from = fields.Float(string='From', default=9.0)
    handover_hour_to = fields.Float(string='To', default=17.0)
    handover_weekdays = fields.Boolean(string='Monday to Friday Only', default=True)
    handover_tz = fields.Selection('_tz_get', string='Time Zone', default=lambda self: self.env.user.tz or 'UTC')
    no_operator_message = fields.Text(
        string='When No Operator Is Available', translate=True,
        default='No colleague is available right now. Leave your email and your question, '
                'and we will come back to you.')
    # limits
    max_replies = fields.Integer(string='Answers per Chat', default=30,
                                 help='After this many answers in one chat, the agent hands over or stops.')
    max_messages_hour = fields.Integer(string='Messages per Visitor per Hour', default=30,
                                       help='Messages of one visitor over all chats in the last hour.')
    max_message_chars = fields.Integer(string='Characters per Message', default=1000,
                                       help='Longer messages are cut before they are sent to the AI.')
    # stats
    conversation_count = fields.Integer(string='Chats', compute='_compute_counts')
    job_count = fields.Integer(string='Answers', compute='_compute_counts')

    @api.model
    def _tz_get(self):
        return [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]

    def _compute_installed_apps(self):
        for agent in self:
            agent.has_crm = 'crm.lead' in self.env
            agent.has_helpdesk = 'om.helpdesk.ticket' in self.env
            agent.has_products = 'product.template' in self.env

    def _compute_counts(self):
        chats = dict(self.env['discuss.channel'].sudo()._read_group(
            [('om_ai_agent_id', 'in', self.ids)], ['om_ai_agent_id'], ['__count']))
        jobs = dict(self.env['om.ai.livechat.job'].sudo()._read_group(
            [('agent_id', 'in', self.ids), ('state', '=', 'done')], ['agent_id'], ['__count']))
        for agent in self:
            agent.conversation_count = chats.get(agent, 0)
            agent.job_count = jobs.get(agent, 0)

    @api.model_create_multi
    def create(self, vals_list):
        agents = super().create(vals_list)
        for agent in agents.filtered(lambda a: not a.partner_id):
            with file_open('om_ai_livechat/static/description/icon.png', 'rb') as image:
                picture = base64.b64encode(image.read()).decode()
            agent.partner_id = self.env['res.partner'].sudo().create({
                'name': agent.name,
                'image_1920': picture,
                'company_id': agent.company_id.id,
            })
        return agents

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            for agent in self:
                agent.partner_id.sudo().name = agent.name
        if 'use_embeddings' in vals:
            self.filtered('use_embeddings').source_ids.chunk_ids._embed()
        return res

    def action_view_conversations(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('im_livechat.discuss_channel_action')
        action['domain'] = [('om_ai_agent_id', '=', self.id)]
        action['context'] = {}
        return action

    def action_view_jobs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Answers'),
            'res_model': 'om.ai.livechat.job',
            'view_mode': 'list,form',
            'domain': [('agent_id', '=', self.id)],
        }

    def action_reindex(self):
        self.source_ids._index()
        return True

    # ------------------------------------------------------------------
    # Hand-over
    # ------------------------------------------------------------------
    def _within_hours(self, now=None):
        self.ensure_one()
        if not self.handover_hours:
            return True
        now = now or fields.Datetime.now()
        local = pytz.utc.localize(now).astimezone(pytz.timezone(self.handover_tz or 'UTC'))
        if self.handover_weekdays and local.weekday() >= 5:
            return False
        hour = local.hour + local.minute / 60.0
        return self.handover_hour_from <= hour < self.handover_hour_to

    def _keywords(self):
        self.ensure_one()
        return [word.strip().lower() for word in (self.handover_keywords or '').split(',') if word.strip()]

    def _visitor_messages_last_hour(self, message):
        """Messages the author of ``message`` posted in live chats over the last hour."""
        domain = [
            ('model', '=', 'discuss.channel'),
            ('message_type', '=', 'comment'),
            ('create_date', '>=', fields.Datetime.now() - timedelta(hours=1)),
        ]
        if message.author_guest_id:
            domain.append(('author_guest_id', '=', message.author_guest_id.id))
        elif message.author_id:
            domain.append(('author_id', '=', message.author_id.id))
        else:
            return 0
        return self.env['mail.message'].sudo().search_count(domain)
