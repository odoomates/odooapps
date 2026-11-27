from odoo import fields, models, tools
from odoo.tools import SQL


class OmAiWhatsappReport(models.Model):
    """ One line per conversation of the assistant: replies, hand-overs,
    quotations and orders made, revenue and the AI cost. """
    _name = 'om.ai.whatsapp.report'
    _description = 'WhatsApp AI Assistant Analysis'
    _auto = False
    _order = 'date desc'

    conversation_id = fields.Many2one('om.ai.whatsapp.conversation', string='Conversation', readonly=True)
    date = fields.Datetime(readonly=True)
    account_id = fields.Many2one('om.whatsapp.account', string='WhatsApp Account', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    state = fields.Selection([('ai', 'Assistant'), ('human', 'Person'), ('stopped', 'Opted Out')], readonly=True)
    conversation_count = fields.Integer('Conversations', readonly=True, aggregator='sum')
    reply_count = fields.Integer('AI Replies', readonly=True, aggregator='sum')
    handover_count = fields.Integer('Hand-overs', readonly=True, aggregator='sum')
    quotation_count = fields.Integer('Quotations', readonly=True, aggregator='sum')
    order_count = fields.Integer('Orders', readonly=True, aggregator='sum')
    revenue = fields.Float('Revenue (Untaxed)', readonly=True, aggregator='sum',
                           help="Untaxed amount of the confirmed orders, in the currency of the company.")
    cost = fields.Float('AI Cost (USD)', readonly=True, aggregator='sum', digits=(16, 4))
    tokens = fields.Integer('AI Tokens', readonly=True, aggregator='sum')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT c.id AS id,
                       c.id AS conversation_id,
                       c.create_date AS date,
                       c.account_id AS account_id,
                       c.company_id AS company_id,
                       c.partner_id AS partner_id,
                       c.state AS state,
                       1 AS conversation_count,
                       c.reply_count AS reply_count,
                       c.handover_count AS handover_count,
                       COALESCE(so.quotations, 0) AS quotation_count,
                       COALESCE(so.orders, 0) AS order_count,
                       COALESCE(so.revenue, 0.0) AS revenue,
                       COALESCE(u.cost, 0.0) AS cost,
                       COALESCE(u.tokens, 0) AS tokens
                  FROM om_ai_whatsapp_conversation c
             LEFT JOIN (
                    SELECT om_ai_whatsapp_conversation_id AS conversation_id,
                           COUNT(*) AS quotations,
                           COUNT(*) FILTER (WHERE state = 'sale') AS orders,
                           SUM(CASE WHEN state = 'sale'
                                    THEN amount_untaxed / COALESCE(NULLIF(currency_rate, 0), 1.0)
                                    ELSE 0 END) AS revenue
                      FROM sale_order
                     WHERE om_ai_whatsapp_conversation_id IS NOT NULL
                  GROUP BY om_ai_whatsapp_conversation_id
                  ) so ON so.conversation_id = c.id
             LEFT JOIN (
                    SELECT om_ai_whatsapp_conversation_id AS conversation_id,
                           SUM(cost) AS cost,
                           SUM(total_tokens) AS tokens
                      FROM om_ai_usage
                     WHERE om_ai_whatsapp_conversation_id IS NOT NULL
                  GROUP BY om_ai_whatsapp_conversation_id
                  ) u ON u.conversation_id = c.id
            )
        """, SQL.identifier(self._table)))
