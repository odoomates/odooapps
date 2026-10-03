from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.misc import format_date


class AccountTaxClosingWizard(models.TransientModel):
    """ Close a tax period: the tax due on the period leaves the tax accounts for the account of the tax owed
    or to be refunded, in a draft entry to review and post. """
    _name = 'account.tax.closing.wizard'
    _description = 'Tax Period Closing'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Start Date', required=True)
    date_to = fields.Date(string='End Date', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, check_company=True, domain=[('type', '=', 'general')],
        default=lambda self: self.env.company.om_tax_closing_journal_id)
    payable_account_id = fields.Many2one(
        'account.account', string='Tax Payable Account', required=True, check_company=True,
        default=lambda self: self.env.company.om_tax_payable_account_id,
        help="Receives the tax owed for the period.")
    receivable_account_id = fields.Many2one(
        'account.account', string='Tax Receivable Account', required=True, check_company=True,
        default=lambda self: self.env.company.om_tax_receivable_account_id,
        help="Receives the tax to be refunded for the period.")

    def _closing_ref(self):
        self.ensure_one()
        return _('Tax closing %(date_from)s - %(date_to)s',
                 date_from=format_date(self.env, self.date_from), date_to=format_date(self.env, self.date_to))

    def _get_closing_domain(self):
        """ The tax lines due on the period: posted, the cash basis taxes on their payment, without the
        withholding taxes, which are owed apart """
        self.ensure_one()
        MoveLine = self.env['account.move.line']
        domain = [
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('tax_line_id', '!=', False),
        ]
        if 'is_withholding_tax_on_payment' in self.env['account.tax']._fields:
            domain.append(('tax_line_id.is_withholding_tax_on_payment', '=', False))
        return expression.AND([domain, MoveLine._get_tax_exigible_domain()])

    def _prepare_move_lines(self):
        self.ensure_one()
        currency = self.company_id.currency_id
        label = self._closing_ref()
        groups = self.env['account.move.line'].read_group(
            self._get_closing_domain(), ['balance:sum'], ['account_id'])
        lines, net = [], 0.0
        for group in groups:
            account, balance = self.env['account.account'].browse(group['account_id'][0]), group['balance']
            if currency.is_zero(balance):
                continue
            net += balance
            lines.append({'name': label, 'account_id': account.id, 'balance': -balance})
        if not lines:
            raise UserError(_('No tax is due on the period: there is nothing to close.'))
        if not currency.is_zero(net):
            # a debit left (net > 0) is tax to be refunded, a credit (net < 0) tax owed
            account = self.receivable_account_id if net > 0 else self.payable_account_id
            lines.append({'name': label, 'account_id': account.id, 'balance': net})
        return lines

    def action_close(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('The start date of the period is after its end date.'))
        ref = self._closing_ref()
        if self.env['account.move'].search_count([
                ('company_id', '=', self.company_id.id), ('journal_id', '=', self.journal_id.id),
                ('ref', '=', ref), ('state', '!=', 'cancel')], limit=1):
            raise UserError(_('The period is already closed: %s.', ref))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'date': self.date_to,
            'ref': ref,
            'line_ids': [fields.Command.create(vals) for vals in self._prepare_move_lines()],
        })
        # proposed again on the next closing
        self.company_id.sudo().write({
            'om_tax_closing_journal_id': self.journal_id.id,
            'om_tax_payable_account_id': self.payable_account_id.id,
            'om_tax_receivable_account_id': self.receivable_account_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tax Closing'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }
