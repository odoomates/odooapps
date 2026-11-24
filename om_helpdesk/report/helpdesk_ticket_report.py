from odoo import fields, models, tools
from odoo.tools import SQL

from odoo.addons.om_helpdesk.models.helpdesk_ticket import TICKET_PRIORITY


class OmHelpdeskTicketReport(models.Model):
    _name = 'om.helpdesk.ticket.report'
    _description = 'Helpdesk Ticket Analysis'
    _auto = False
    _rec_name = 'ticket_id'
    _order = 'date_open desc'

    ticket_id = fields.Many2one('om.helpdesk.ticket', string='Ticket', readonly=True)
    number = fields.Char(string='Ticket Number', readonly=True)
    team_id = fields.Many2one('om.helpdesk.team', string='Team', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    stage_id = fields.Many2one('om.helpdesk.stage', string='Stage', readonly=True)
    ticket_type_id = fields.Many2one('om.helpdesk.ticket.type', string='Type', readonly=True)
    priority = fields.Selection(TICKET_PRIORITY, readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    is_closed = fields.Boolean(string='Closed', readonly=True)
    sla_state = fields.Selection([
        ('none', 'No SLA'),
        ('ongoing', 'On Time'),
        ('reached', 'Reached'),
        ('failed', 'Failed'),
    ], string='SLA', readonly=True)
    date_open = fields.Datetime(string='Opened On', readonly=True)
    date_closed = fields.Datetime(string='Closed On', readonly=True)
    ticket_count = fields.Integer(string='# Tickets', readonly=True)
    open_count = fields.Integer(string='# Open', readonly=True)
    closed_count = fields.Integer(string='# Closed', readonly=True)
    hours_to_assign = fields.Float(string='Hours to Assign', readonly=True, aggregator='avg')
    hours_to_first_response = fields.Float(string='Hours to First Response', readonly=True, aggregator='avg')
    hours_to_close = fields.Float(string='Hours to Close', readonly=True, aggregator='avg')
    sla_success_rate = fields.Float(
        string='SLA Success (%)', readonly=True, aggregator='avg',
        help="Share of tickets with an SLA that did not fail any of them.")
    rating = fields.Float(string='Rating (1-5)', readonly=True, aggregator='avg')

    def _select(self):
        return SQL("""
            t.id AS id,
            t.id AS ticket_id,
            t.number AS number,
            t.team_id AS team_id,
            t.user_id AS user_id,
            t.commercial_partner_id AS partner_id,
            t.stage_id AS stage_id,
            t.ticket_type_id AS ticket_type_id,
            t.priority AS priority,
            t.company_id AS company_id,
            t.is_closed AS is_closed,
            t.sla_state AS sla_state,
            t.date_open AS date_open,
            t.date_closed AS date_closed,
            1 AS ticket_count,
            CASE WHEN t.is_closed THEN 0 ELSE 1 END AS open_count,
            CASE WHEN t.is_closed THEN 1 ELSE 0 END AS closed_count,
            CASE WHEN t.date_assign IS NOT NULL
                 THEN EXTRACT(EPOCH FROM (t.date_assign - t.date_open)) / 3600 END AS hours_to_assign,
            CASE WHEN t.date_first_response IS NOT NULL
                 THEN EXTRACT(EPOCH FROM (t.date_first_response - t.date_open)) / 3600 END AS hours_to_first_response,
            CASE WHEN t.date_closed IS NOT NULL
                 THEN EXTRACT(EPOCH FROM (t.date_closed - t.date_open)) / 3600 END AS hours_to_close,
            CASE WHEN t.sla_state = 'failed' THEN 0
                 WHEN t.sla_state IN ('ongoing', 'reached') THEN 100 END AS sla_success_rate,
            CASE WHEN t.rating_last_value > 0 THEN t.rating_last_value END AS rating
        """)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL(
            "CREATE OR REPLACE VIEW %s AS (SELECT %s FROM om_helpdesk_ticket t WHERE t.active)",
            SQL.identifier(self._table),
            self._select(),
        ))
