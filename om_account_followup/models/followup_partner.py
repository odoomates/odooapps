from odoo import api, fields, models
from odoo import tools
from odoo.tools import SQL

# partner ids are PostgreSQL integers, so they always stay below this offset
STAT_ID_COMPANY_OFFSET = 2 ** 31


class FollowupStatByPartner(models.Model):
    _name = "followup.stat.by.partner"
    _description = "Follow-up Statistics by Partner"
    _rec_name = 'partner_id'
    _auto = False
    _depends = {
        'account.move.line': [
            'account_id', 'company_id', 'credit', 'date', 'debit',
            'followup_date', 'followup_line_id', 'full_reconcile_id', 'partner_id',
        ],
        'account.account': ['account_type'],
        'followup.line': ['delay'],
    }

    def _get_invoice_partner_id(self):
        for rec in self:
            rec.invoice_partner_id = rec.partner_id.address_get(
                adr_pref=['invoice']).get('invoice', rec.partner_id.id)

    partner_id = fields.Many2one('res.partner', 'Partner', readonly=True)
    date_move = fields.Date('First move', readonly=True)
    date_move_last = fields.Date('Last move', readonly=True)
    date_followup = fields.Date('Latest follow-up', readonly=True)
    max_followup_id = fields.Many2one('followup.line', 'Max Follow Up Level', readonly=True, ondelete="cascade")
    balance = fields.Float('Balance', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)
    invoice_partner_id = fields.Many2one('res.partner', compute='_get_invoice_partner_id', string='Invoice Address')

    @api.model
    def _get_stat_id(self, partner_id, company_id):
        """ Id of the statistics line of `partner_id` in `company_id`. """
        return company_id * STAT_ID_COMPANY_OFFSET + partner_id

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'followup_stat_by_partner')
        self.env.cr.execute(SQL("""
            create view followup_stat_by_partner as (
                SELECT
                    l.company_id::bigint * %s + l.partner_id as id,
                    l.partner_id AS partner_id,
                    min(l.date) AS date_move,
                    max(l.date) AS date_move_last,
                    max(l.followup_date) AS date_followup,
                    (array_agg(l.followup_line_id ORDER BY fl.delay DESC NULLS LAST))[1] AS max_followup_id,
                    sum(l.debit - l.credit) AS balance,
                    l.company_id as company_id
                FROM
                    account_move_line l
                    LEFT JOIN account_account a ON (l.account_id = a.id)
                    LEFT JOIN followup_line fl ON (l.followup_line_id = fl.id)
                WHERE
                    a.account_type = 'asset_receivable' AND
                    l.full_reconcile_id is NULL AND
                    l.partner_id IS NOT NULL
                    GROUP BY
                    l.partner_id, l.company_id
            )""", STAT_ID_COMPANY_OFFSET))
