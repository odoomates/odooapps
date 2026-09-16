from datetime import timedelta

from odoo import api, fields, models, _


class AccountFiscalYearClosing(models.TransientModel):
    _name = 'account.fiscal.year.closing'
    _description = 'Close Fiscal Year'
    _check_company_auto = True

    fiscal_year_id = fields.Many2one('account.fiscal.year', string='Fiscal Year', required=True, readonly=True)
    company_id = fields.Many2one(related='fiscal_year_id.company_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(string='Closing Entry Date', required=True,
                       compute='_compute_date', store=True, readonly=False, precompute=True,
                       help='By default the first day after the fiscal year, so that the balance sheet at the end '
                            'of the year still shows its earnings.')
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, check_company=True,
                                 domain=[('type', '=', 'general')],
                                 compute='_compute_journal_id', store=True, readonly=False, precompute=True)
    retained_earnings_account_id = fields.Many2one(
        'account.account', string='Retained Earnings Account', required=True, check_company=True,
        domain=[('account_type', '=', 'equity')],
        compute='_compute_retained_earnings_account_id', store=True, readonly=False, precompute=True,
        help='Equity account receiving the earnings. Accounts of type Current Year Earnings cannot be used: '
             'their balance is not carried forward to the next fiscal years.')
    unaffected_earnings_account_id = fields.Many2one(
        'account.account', string='Transfer From', required=True, check_company=True,
        domain=[('account_type', '=', 'equity_unaffected')],
        compute='_compute_unaffected_earnings_account_id', store=True, readonly=False, precompute=True,
        help='Account of type Current Year Earnings debited (or credited for a loss) by the closing entry.')
    lock = fields.Boolean(string='Lock the Fiscal Year', default=True,
                          help='Set the global lock date to the end of the fiscal year once it is closed.')

    earnings = fields.Monetary(string='Earnings to Transfer', compute='_compute_checklist',
                               help='Profit (positive) or loss (negative) of this fiscal year and of the previous '
                                    'ones not transferred to the retained earnings yet.')
    draft_move_count = fields.Integer(compute='_compute_checklist')
    unreconciled_statement_line_count = fields.Integer(compute='_compute_checklist')
    open_previous_year_count = fields.Integer(compute='_compute_checklist')
    blocking_issues = fields.Text(compute='_compute_checklist')

    @api.depends('fiscal_year_id')
    def _compute_date(self):
        for wizard in self:
            wizard.date = wizard.fiscal_year_id.date_to and wizard.fiscal_year_id.date_to + timedelta(days=1)

    @api.depends('company_id')
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = self.env['account.journal'].search([
                *self.env['account.journal']._check_company_domain(wizard.company_id),
                ('type', '=', 'general'),
            ], limit=1)

    @api.depends('company_id')
    def _compute_retained_earnings_account_id(self):
        for wizard in self:
            wizard.retained_earnings_account_id = wizard.company_id.retained_earnings_account_id

    @api.depends('company_id')
    def _compute_unaffected_earnings_account_id(self):
        for wizard in self:
            wizard.unaffected_earnings_account_id = wizard.company_id and wizard.company_id.get_unaffected_earnings_account()

    @api.depends('fiscal_year_id', 'lock')
    def _compute_checklist(self):
        for wizard in self:
            fiscal_year = wizard.fiscal_year_id
            if not fiscal_year:
                wizard.update({'earnings': 0.0, 'draft_move_count': 0, 'unreconciled_statement_line_count': 0,
                               'open_previous_year_count': 0, 'blocking_issues': False})
                continue
            wizard.earnings = -fiscal_year._get_unallocated_earnings()
            wizard.draft_move_count = self.env['account.move'].search_count(fiscal_year._get_draft_moves_domain())
            wizard.unreconciled_statement_line_count = self.env['account.bank.statement.line'].search_count(
                fiscal_year._get_unreconciled_statement_lines_domain())
            wizard.open_previous_year_count = self.env['account.fiscal.year'].search_count([
                ('company_id', '=', fiscal_year.company_id.id),
                ('date_to', '<', fiscal_year.date_from),
                ('state', '=', 'open'),
            ])
            wizard.blocking_issues = '\n'.join(fiscal_year._get_closing_blocking_issues(wizard.lock)) or False

    def action_close(self):
        self.ensure_one()
        self.fiscal_year_id._close(self.journal_id, self.retained_earnings_account_id, self.date, lock=self.lock,
                                   unaffected_earnings_account=self.unaffected_earnings_account_id)
        return {'type': 'ir.actions.act_window_close'}

    def action_view_draft_moves(self):
        self.ensure_one()
        return {
            'name': _('Draft Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': self.fiscal_year_id._get_draft_moves_domain(),
        }

    def action_view_unreconciled_statement_lines(self):
        self.ensure_one()
        return {
            'name': _('Unreconciled Bank Transactions'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.bank.statement.line',
            'view_mode': 'list,form',
            'domain': self.fiscal_year_id._get_unreconciled_statement_lines_domain(),
        }
