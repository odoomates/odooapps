from odoo import fields, models
from odoo.tools.sql import SQL, drop_view_if_exists

from ..models.sale_order import SUBSCRIPTION_STATES


class OmSubscriptionReport(models.Model):
    _name = 'om.subscription.report'
    _description = 'Subscription Analysis'
    _auto = False
    _order = 'start_date desc'
    _rec_name = 'name'

    order_id = fields.Many2one('sale.order', string='Subscription', readonly=True)
    name = fields.Char(string='Reference', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    country_id = fields.Many2one('res.country', string='Customer Country', readonly=True)
    plan_id = fields.Many2one('om.subscription.plan', string='Recurring Plan', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    team_id = fields.Many2one('crm.team', string='Sales Team', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    subscription_state = fields.Selection(SUBSCRIPTION_STATES, string='Subscription Status', readonly=True)
    subscription_type = fields.Selection([('new', 'New'), ('renewal', 'Renewal')], readonly=True)
    health = fields.Selection([('normal', 'Neutral'), ('done', 'Good'), ('blocked', 'At Risk')], readonly=True)
    close_reason_id = fields.Many2one('om.subscription.close.reason', readonly=True)
    start_date = fields.Date(readonly=True)
    close_date = fields.Date(string='Closed On', readonly=True)
    next_invoice_date = fields.Date(string='Next Invoice', readonly=True)
    recurring_total = fields.Monetary(readonly=True)
    mrr = fields.Monetary(string='Monthly Recurring Revenue', readonly=True)
    arr = fields.Monetary(string='Annual Recurring Revenue', readonly=True)
    retention_rate = fields.Float(string='Retention (%)', aggregator='avg', readonly=True,
                                  help='Share of the subscriptions still running (in progress, paused or renewed).')
    churn_rate = fields.Float(string='Churn (%)', aggregator='avg', readonly=True,
                              help='Share of the subscriptions closed.')

    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    so.id AS id,
                    so.id AS order_id,
                    so.name AS name,
                    so.partner_id AS partner_id,
                    partner.country_id AS country_id,
                    so.subscription_plan_id AS plan_id,
                    so.user_id AS user_id,
                    so.team_id AS team_id,
                    so.company_id AS company_id,
                    so.currency_id AS currency_id,
                    so.subscription_state AS subscription_state,
                    so.subscription_type AS subscription_type,
                    so.subscription_health AS health,
                    so.subscription_close_reason_id AS close_reason_id,
                    so.subscription_start_date AS start_date,
                    so.subscription_close_date AS close_date,
                    so.subscription_next_invoice_date AS next_invoice_date,
                    so.subscription_recurring_total AS recurring_total,
                    CASE WHEN so.subscription_state IN ('progress', 'paused') THEN so.subscription_mrr ELSE 0 END AS mrr,
                    CASE WHEN so.subscription_state IN ('progress', 'paused') THEN so.subscription_arr ELSE 0 END AS arr,
                    CASE WHEN so.subscription_state IN ('progress', 'paused', 'renewed') THEN 100.0 ELSE 0.0 END
                        AS retention_rate,
                    CASE WHEN so.subscription_state = 'churn' THEN 100.0 ELSE 0.0 END AS churn_rate
                FROM sale_order so
                LEFT JOIN res_partner partner ON partner.id = so.partner_id
                WHERE so.is_subscription
                  AND so.state = 'sale'
            )
        """, SQL.identifier(self._table)))
