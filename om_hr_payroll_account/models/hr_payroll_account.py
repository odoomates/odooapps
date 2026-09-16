from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


def _default_salary_journal(records):
    # the payroll users may have no accounting rights: only the journal of the company is looked up
    company = records.env.company
    journal = records.env['account.journal'].sudo().search([
        ('type', '=', 'general'), ('company_id', '=', company.id),
    ], limit=1)
    return journal.id


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    def _get_partner_id(self, credit_account):
        """
        Get partner_id of slip line to use in account_move_line
        """
        # use partner of salary rule or fallback on employee's address
        register_partner_id = self.salary_rule_id.register_id.partner_id
        partner_id = register_partner_id.id
        if credit_account:
            if register_partner_id or self.salary_rule_id.account_credit.account_type in (
                    'asset_receivable', 'liability_payable'):
                return partner_id
        else:
            if register_partner_id or self.salary_rule_id.account_debit.account_type in (
                    'asset_receivable', 'liability_payable'):
                return partner_id
        return False


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    date = fields.Date(
        'Date Account', help="Keep empty to use the period of the validation(Payslip) date."
    )
    journal_id = fields.Many2one(
        'account.journal', 'Salary Journal', required=True, default=_default_salary_journal,
        domain="[('company_id', '=', company_id)]",
    )
    move_id = fields.Many2one('account.move', 'Accounting Entry', readonly=True, copy=False)

    @api.constrains('journal_id', 'company_id')
    def _check_journal_company(self):
        for slip in self:
            if slip.company_id and slip.journal_id.sudo().company_id != slip.company_id:
                raise ValidationError(_('The salary journal of the payslip %(payslip)s must belong to %(company)s.',
                                        payslip=slip.name or slip.number or '', company=slip.company_id.name))

    def _get_company_salary_journal(self):
        self.ensure_one()
        journal = self.version_id.journal_id
        if journal.sudo().company_id == self.company_id:
            return journal
        if self.journal_id.sudo().company_id == self.company_id:
            return self.journal_id
        return self.env['account.journal'].browse(_default_salary_journal(self.with_company(self.company_id)))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.context.get('journal_id'):
                vals.setdefault('journal_id', self.env.context['journal_id'])
            if not vals.get('journal_id') and vals.get('company_id'):
                # the default journal is the one of the company of the payslip, not of the current company
                journal_id = _default_salary_journal(self.with_company(vals['company_id']))
                if journal_id:
                    vals['journal_id'] = journal_id
        return super().create(vals_list)

    @api.onchange('version_id')
    def onchange_version(self):
        super().onchange_version()
        self.journal_id = self._get_company_salary_journal()

    @api.onchange('employee_id', 'date_from', 'date_to')
    def onchange_employee(self):
        res = super().onchange_employee()
        if self.company_id and self.journal_id.sudo().company_id != self.company_id:
            self.journal_id = self._get_company_salary_journal()
        return res

    def action_payslip_cancel(self):
        self._check_own_payslip()
        for slip in self.filtered('move_id'):
            move = slip.move_id.sudo()
            if move.reversal_move_ids.filtered(lambda reversal: reversal.state == 'posted'):
                # already cancelled in the books by a reversal: the entry stays
                continue
            try:
                with self.env.cr.savepoint():
                    if move.state == 'posted':
                        move.button_draft()
                    move.unlink()
            except UserError as error:
                raise UserError(_(
                    'The accounting entry %(entry)s of the payslip %(payslip)s cannot be deleted: %(reason)s\n'
                    'Reverse the entry in Accounting, then cancel the payslip.',
                    entry=move.display_name, payslip=slip.number or slip.name or '', reason=error.args[0],
                )) from error
        return super().action_payslip_cancel()

    def action_payslip_done(self):
        res = super().action_payslip_done()

        for slip in self:
            line_ids = []
            debit_sum = 0.0
            credit_sum = 0.0
            date = slip.date or slip.date_to
            currency = slip.company_id.currency_id

            name = _('Payslip of %s') % (slip.employee_id.name)
            journal = slip.journal_id.sudo()
            if journal.company_id != slip.company_id:
                raise UserError(_('The salary journal %(journal)s does not belong to the company of the '
                                  'payslip %(payslip)s.',
                                  journal=journal.name, payslip=slip.number or slip.name or ''))
            move_dict = {
                'narration': name,
                'ref': slip.number,
                'journal_id': slip.journal_id.id,
                'company_id': slip.company_id.id,
                'date': date,
            }
            if not any(line.salary_rule_id.account_debit and line.salary_rule_id.account_credit
                       for line in slip.details_by_salary_rule_category):
                raise UserError(_('Missing Debit Or Credit Account in Salary Rule'))
            for line in slip.details_by_salary_rule_category:
                amount = currency.round(slip.credit_note and -line.total or line.total)
                if currency.is_zero(amount):
                    continue

                debit_account_id = line.salary_rule_id.account_debit.id
                credit_account_id = line.salary_rule_id.account_credit.id
                if debit_account_id:
                    debit_line = (0, 0, {
                        'name': line.name,
                        'partner_id': line._get_partner_id(credit_account=False),
                        'account_id': debit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'debit': amount > 0.0 and amount or 0.0,
                        'credit': amount < 0.0 and -amount or 0.0,
                        'analytic_distribution': ({line.salary_rule_id.analytic_account_id.id: 100}
                                                  if line.salary_rule_id.analytic_account_id else {}),
                        'tax_line_id': line.salary_rule_id.account_tax_id.id,
                    })
                    line_ids.append(debit_line)
                    debit_sum += debit_line[2]['debit'] - debit_line[2]['credit']

                if credit_account_id:
                    credit_line = (0, 0, {
                        'name': line.name,
                        'partner_id': line._get_partner_id(credit_account=True),
                        'account_id': credit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'debit': amount < 0.0 and -amount or 0.0,
                        'credit': amount > 0.0 and amount or 0.0,
                        'analytic_distribution': ({line.salary_rule_id.analytic_account_id.id: 100}
                                                  if line.salary_rule_id.analytic_account_id else {}),
                        'tax_line_id': line.salary_rule_id.account_tax_id.id,
                    })
                    line_ids.append(credit_line)
                    credit_sum += credit_line[2]['credit'] - credit_line[2]['debit']

            if currency.compare_amounts(credit_sum, debit_sum) == -1:
                acc_id = slip.journal_id.default_account_id.id
                if not acc_id:
                    raise UserError(_('The Expense Journal "%s" has not properly configured the Credit Account!')
                                    % (slip.journal_id.name))
                adjust_credit = (0, 0, {
                    'name': _('Adjustment Entry'),
                    'partner_id': False,
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'debit': 0.0,
                    'credit': currency.round(debit_sum - credit_sum),
                })
                line_ids.append(adjust_credit)

            elif currency.compare_amounts(debit_sum, credit_sum) == -1:
                acc_id = slip.journal_id.default_account_id.id
                if not acc_id:
                    raise UserError(_('The Expense Journal "%s" has not properly configured the Debit Account!')
                                    % (slip.journal_id.name))
                adjust_debit = (0, 0, {
                    'name': _('Adjustment Entry'),
                    'partner_id': False,
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'debit': currency.round(credit_sum - debit_sum),
                    'credit': 0.0,
                })
                line_ids.append(adjust_debit)
            move_dict['line_ids'] = line_ids
            # the payroll users may have no accounting rights: the entry follows the configuration of the rules
            move = self.env['account.move'].sudo().with_company(slip.company_id).create(move_dict)
            slip.write({'move_id': move.id, 'date': date})
            move.action_post()
        return res


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    analytic_account_id = fields.Many2one('account.analytic.account', 'Analytic Account')
    account_tax_id = fields.Many2one('account.tax', 'Tax')
    account_debit = fields.Many2one('account.account', 'Debit Account', )
    account_credit = fields.Many2one('account.account', 'Credit Account')


class HrVersion(models.Model):
    _inherit = 'hr.version'
    _description = 'Employee Contract'

    analytic_account_id = fields.Many2one('account.analytic.account', 'Analytic Account')
    journal_id = fields.Many2one('account.journal', 'Salary Journal')


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    journal_id = fields.Many2one(
        'account.journal', 'Salary Journal', required=True, default=_default_salary_journal,
        domain="[('company_id', '=', company_id)]",
    )
