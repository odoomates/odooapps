from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountFiscalYear(models.Model):
    _name = 'account.fiscal.year'
    _description = 'Fiscal Year'
    _order = 'date_from desc'

    name = fields.Char(string='Name', required=True)
    date_from = fields.Date(string='Start Date', required=True,
        help='Start Date, included in the fiscal year.')
    date_to = fields.Date(string='End Date', required=True,
        help='Ending Date, included in the fiscal year.')
    company_id = fields.Many2one('res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    state = fields.Selection([('open', 'Open'), ('closed', 'Closed')], string='Status',
        default='open', required=True, readonly=True, copy=False)
    closing_move_id = fields.Many2one('account.move', string='Closing Entry', readonly=True, copy=False,
        help='Entry transferring the earnings of the fiscal year to the retained earnings.')

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_dates(self):
        '''
        Check interleaving between fiscal years.
        There are 3 cases to consider:

        s1   s2   e1   e2
        (    [----)----]

        s2   s1   e2   e1
        [----(----]    )

        s1   s2   e2   e1
        (    [----]    )
        '''
        for fy in self:
            # Starting date must be prior to the ending date
            date_from = fy.date_from
            date_to = fy.date_to
            if date_to < date_from:
                raise ValidationError(_('The ending date must not be prior to the starting date.'))
            domain = [
                ('id', '!=', fy.id),
                ('company_id', '=', fy.company_id.id),
                '|', '|',
                '&', ('date_from', '<=', fy.date_from), ('date_to', '>=', fy.date_from),
                '&', ('date_from', '<=', fy.date_to), ('date_to', '>=', fy.date_to),
                '&', ('date_from', '<=', fy.date_from), ('date_to', '>=', fy.date_to),
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(_('You can not have an overlap between two fiscal years, '
                                        'please correct the start and/or end dates of your fiscal years.'))

    def write(self, vals):
        if {'date_from', 'date_to', 'company_id'} & set(vals) and self.filtered(lambda fy: fy.state == 'closed'):
            raise UserError(_('The dates and the company of a closed fiscal year cannot be changed. Reopen it first.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_closed(self):
        if self.filtered(lambda fy: fy.state == 'closed'):
            raise UserError(_('A closed fiscal year cannot be deleted. Reopen it first.'))

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only accounting administrators can close or reopen a fiscal year.'))

    def _get_unallocated_earnings_domain(self):
        """ Journal items whose balance is not yet allocated to the retained earnings at the end of the
        fiscal year: the income and expense of this year and of the previous ones, and the unaffected
        earnings account where the earlier closings were recorded. """
        self.ensure_one()
        domain = [
            ('company_id', 'child_of', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '<=', self.date_to),
            ('account_id.include_initial_balance', '=', False),
        ]
        if self.closing_move_id:
            domain.append(('move_id', '!=', self.closing_move_id.id))
        return domain

    def _get_unallocated_earnings(self):
        """ :return: the balance (debit - credit) of the unallocated earnings, in company currency.
        A profit is a negative balance. """
        self.ensure_one()
        [(balance,)] = self.env['account.move.line'].sudo()._read_group(
            self._get_unallocated_earnings_domain(), aggregates=['balance:sum'])
        return self.company_id.currency_id.round(balance or 0.0)

    def _get_closing_blocking_issues(self, lock):
        self.ensure_one()
        issues = []
        if self.state == 'closed':
            issues.append(_('The fiscal year %s is already closed.', self.name))
        if self.env['account.move'].search_count(self._get_draft_moves_domain(), limit=1):
            issues.append(_('Post or delete the draft journal entries of the fiscal year first.'))
        if lock and self.env['account.bank.statement.line'].search_count(
                self._get_unreconciled_statement_lines_domain(), limit=1):
            issues.append(_('Reconcile the bank statement lines of the fiscal year before locking it.'))
        return issues

    def _get_draft_moves_domain(self):
        self.ensure_one()
        return [
            ('company_id', 'child_of', self.company_id.id),
            ('state', '=', 'draft'),
            ('date', '<=', self.date_to),
        ]

    def _get_unreconciled_statement_lines_domain(self):
        self.ensure_one()
        return self.company_id._get_unreconciled_statement_lines_domain(self.date_to)

    def _close(self, journal, retained_earnings_account, closing_date, lock=True, unaffected_earnings_account=None):
        """ Transfer the unallocated earnings from `unaffected_earnings_account` (by default the one of the
        company) to `retained_earnings_account` with an entry dated `closing_date`, then optionally lock
        the fiscal year. """
        self.ensure_one()
        self._check_manager()
        issues = self._get_closing_blocking_issues(lock)
        if issues:
            raise UserError('\n'.join(issues))
        if closing_date < self.date_to:
            raise UserError(_('The closing entry cannot be dated before the end of the fiscal year.'))
        company = self.company_id
        unaffected_earnings_account = unaffected_earnings_account or company.get_unaffected_earnings_account()
        if unaffected_earnings_account.account_type != 'equity_unaffected':
            raise UserError(_('The earnings are transferred from an account of type Current Year Earnings.'))
        if retained_earnings_account.account_type != 'equity':
            # the balance of the other equity types is not carried forward to the next fiscal years
            raise UserError(_('The retained earnings account %s must be an Equity account.',
                              retained_earnings_account.display_name))

        balance = self._get_unallocated_earnings()
        closing_move = self.env['account.move']
        if not company.currency_id.is_zero(balance):
            label = _('Year-end closing %s', self.name)
            closing_move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'company_id': company.id,
                'date': closing_date,
                'ref': label,
                'line_ids': [
                    fields.Command.create({
                        'name': label,
                        'account_id': unaffected_earnings_account.id,
                        'balance': -balance,
                    }),
                    fields.Command.create({
                        'name': label,
                        'account_id': retained_earnings_account.id,
                        'balance': balance,
                    }),
                ],
            })
            closing_move.action_post()

        company.retained_earnings_account_id = retained_earnings_account
        self.write({'state': 'closed', 'closing_move_id': closing_move.id})
        if lock and (not company.fiscalyear_lock_date or company.fiscalyear_lock_date < self.date_to):
            company.sudo().fiscalyear_lock_date = self.date_to
        return closing_move

    def action_open_closing_wizard(self):
        self.ensure_one()
        self._check_manager()
        return {
            'name': _('Close Fiscal Year'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.fiscal.year.closing',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_fiscal_year_id': self.id},
        }

    def action_reopen(self):
        """ Reverse the closing entry. The lock dates are left untouched: lower them first when the
        closing entry is in a locked period. """
        self._check_manager()
        for fy in self:
            if fy.state != 'closed':
                continue
            if fy.closing_move_id.state == 'posted':
                fy.closing_move_id._reverse_moves(default_values_list=[{
                    'date': fy.closing_move_id.date,
                    'ref': _('Reopening of %s', fy.name),
                }], cancel=True)
            fy.write({'state': 'open', 'closing_move_id': False})
        return True

    def action_view_closing_move(self):
        self.ensure_one()
        return {
            'name': _('Closing Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.closing_move_id.id,
        }
