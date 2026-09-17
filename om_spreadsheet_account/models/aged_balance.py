from odoo import fields, models, tools

BUCKETS = [
    ('not_due', 'Not Due'),
    ('1_30', '1-30 Days'),
    ('31_60', '31-60 Days'),
    ('61_90', '61-90 Days'),
    ('over_90', 'Over 90 Days'),
]


class OmSpreadsheetAgedBalance(models.Model):
    """ The open items of the customers and of the vendors, by age.

    The age depends on today: a pivot of a dashboard cannot compute it from a stored domain, so the view computes it
    each time it is read. The amounts are positive for what the customers owe and for what is owed to the vendors.
    """
    _name = 'om.spreadsheet.aged.balance'
    _description = 'Aged Balance'
    _auto = False
    _order = 'date_maturity, id'
    # written to the database before the view is read
    _depends = {
        'account.move.line': [
            'move_id', 'partner_id', 'account_id', 'company_id', 'date', 'date_maturity', 'parent_state',
            'reconciled', 'amount_residual',
        ],
        'account.account': ['account_type'],
        'res.company': ['currency_id'],
    }

    move_line_id = fields.Many2one('account.move.line', string='Journal Item', readonly=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    date = fields.Date(readonly=True)
    date_maturity = fields.Date(string='Due Date', readonly=True)
    partner_type = fields.Selection(
        [('customer', 'Customer'), ('vendor', 'Vendor')], string='Partner Type', readonly=True)
    bucket = fields.Selection(BUCKETS, string='Age', readonly=True)
    days_overdue = fields.Integer(string='Days Overdue', readonly=True, aggregator='max')
    amount_residual = fields.Monetary(string='Amount Due', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT line.id,
                       line.id AS move_line_id,
                       line.move_id,
                       line.partner_id,
                       line.account_id,
                       line.company_id,
                       company.currency_id,
                       line.date,
                       COALESCE(line.date_maturity, line.date) AS date_maturity,
                       CASE WHEN account.account_type = 'asset_receivable' THEN 'customer' ELSE 'vendor' END
                           AS partner_type,
                       GREATEST(CURRENT_DATE - COALESCE(line.date_maturity, line.date), 0) AS days_overdue,
                       CASE
                           WHEN COALESCE(line.date_maturity, line.date) >= CURRENT_DATE THEN 'not_due'
                           WHEN CURRENT_DATE - COALESCE(line.date_maturity, line.date) <= 30 THEN '1_30'
                           WHEN CURRENT_DATE - COALESCE(line.date_maturity, line.date) <= 60 THEN '31_60'
                           WHEN CURRENT_DATE - COALESCE(line.date_maturity, line.date) <= 90 THEN '61_90'
                           ELSE 'over_90'
                       END AS bucket,
                       CASE WHEN account.account_type = 'asset_receivable'
                            THEN line.amount_residual ELSE -line.amount_residual END AS amount_residual
                  FROM account_move_line line
                  JOIN account_account account ON account.id = line.account_id
                  JOIN res_company company ON company.id = line.company_id
                 WHERE line.parent_state = 'posted'
                   AND account.account_type IN ('asset_receivable', 'liability_payable')
                   AND NOT line.reconciled
                   AND line.amount_residual != 0
            )
        """ % self._table)
