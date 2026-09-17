from odoo import api, fields, models
from odoo import tools
from odoo.tools import SQL

from ..models.followup_partner import STAT_ID_COMPANY_OFFSET


class AccountFollowupStat(models.Model):
    """ The open items of the customers, one line per customer and company: what is due, what is overdue and the
    follow-up level reached. The disputed invoices are left out. """
    _name = "followup.stat"
    _description = "Follow-up Statistics"
    _rec_name = 'partner_id'
    _order = 'balance_overdue desc, id'
    _auto = False
    _depends = {
        'account.move.line': [
            'account_id', 'company_id', 'date', 'date_maturity', 'amount_residual', 'reconciled',
            'parent_state', 'followup_date', 'followup_line_id', 'partner_id', 'move_id',
        ],
        'account.move': ['followup_disputed'],
        'account.account': ['account_type'],
        'followup.line': ['delay'],
    }

    partner_id = fields.Many2one('res.partner', 'Customer', readonly=True)
    date_move = fields.Date('First Open Item', readonly=True)
    date_move_last = fields.Date('Last Open Item', readonly=True)
    date_followup = fields.Date('Latest Follow-up', readonly=True)
    followup_id = fields.Many2one('followup.line', 'Follow-up Level', readonly=True)
    balance = fields.Float('Amount Due', readonly=True)
    balance_overdue = fields.Float('Amount Overdue', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'followup_stat')
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW followup_stat AS (
                SELECT
                    l.company_id::bigint * %s + l.partner_id AS id,
                    l.partner_id AS partner_id,
                    min(l.date) AS date_move,
                    max(l.date) AS date_move_last,
                    max(l.followup_date) AS date_followup,
                    (array_agg(l.followup_line_id ORDER BY fl.delay DESC NULLS LAST))[1] AS followup_id,
                    sum(l.amount_residual) AS balance,
                    sum(CASE WHEN COALESCE(l.date_maturity, l.date) <= CURRENT_DATE
                             THEN l.amount_residual ELSE 0 END) AS balance_overdue,
                    l.company_id AS company_id
                FROM account_move_line l
                JOIN account_account a ON a.id = l.account_id
                JOIN account_move m ON m.id = l.move_id
                LEFT JOIN followup_line fl ON fl.id = l.followup_line_id
                WHERE a.account_type = 'asset_receivable'
                  AND l.parent_state = 'posted'
                  AND NOT l.reconciled
                  AND l.amount_residual != 0
                  AND l.partner_id IS NOT NULL
                  AND NOT COALESCE(m.followup_disputed, FALSE)
                GROUP BY l.partner_id, l.company_id
            )""", STAT_ID_COMPANY_OFFSET))
