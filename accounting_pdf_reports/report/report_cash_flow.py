import time
from collections import defaultdict

from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.fields import Domain

# Section and line of the statement for the cash paid or received against an account of a type, when the
# account does not choose its section
TYPE_FLOWS = {
    'asset_receivable': ('operating', 'receivable'),
    'liability_payable': ('operating', 'payable'),
    'income': ('operating', 'income'),
    'income_other': ('operating', 'income'),
    'expense': ('operating', 'expense'),
    'expense_other': ('operating', 'expense'),
    'expense_direct_cost': ('operating', 'expense'),
    'expense_depreciation': ('operating', 'expense'),
    'liability_current': ('operating', 'current_liability'),
    'asset_current': ('operating', 'current_asset'),
    'asset_prepayments': ('operating', 'current_asset'),
    'liability_credit_card': ('operating', 'credit_card'),
    'asset_fixed': ('investing', 'fixed_asset'),
    'asset_non_current': ('investing', 'fixed_asset'),
    'liability_non_current': ('financing', 'borrowing'),
    'equity': ('financing', 'equity'),
    'equity_unaffected': ('financing', 'equity'),
}
LINE_ORDER = (
    'receivable', 'payable', 'income', 'expense', 'current_liability', 'current_asset', 'credit_card',
    'unmatched', 'transfer', 'fixed_asset', 'borrowing', 'equity', 'other',
)
# The cash is followed through the reconciliations of the transit accounts (outstanding receipts and payments,
# suspense, internal transfers) to find what it was paid for, this many steps at most.
MAX_TRANSIT_DEPTH = 4


class ReportCashFlow(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_cash_flow'
    _description = 'Cash Flow Statement'

    @api.model
    def _get_line_labels(self):
        return {
            'receivable': _('Cash received from customers'),
            'payable': _('Cash paid to suppliers'),
            'income': _('Other income received'),
            'expense': _('Expenses paid'),
            'current_liability': _('Taxes, salaries and other current liabilities'),
            'current_asset': _('Other current assets'),
            'credit_card': _('Credit cards'),
            'unmatched': _('Payments not matched yet'),
            'transfer': _('Cash in transit between cash accounts'),
            'fixed_asset': _('Fixed and non-current assets'),
            'borrowing': _('Borrowings'),
            'equity': _('Equity'),
            'other': _('Other'),
        }

    @api.model
    def _get_transit_accounts(self, company):
        journals = self.env['account.journal'].sudo().search([('company_id', 'child_of', company.id)])
        method_lines = self.env['account.payment.method.line'].sudo().search([('journal_id', 'in', journals.ids)])
        return (company.transfer_account_id | company.account_journal_suspense_account_id
                | journals.suspense_account_id | method_lines.payment_account_id).sudo(False)

    @api.model
    def _get_line_domain(self, form, company):
        states = ('posted',) if form['target_move'] == 'posted' else ('draft', 'posted')
        domain = Domain('company_id', 'child_of', company.id) & Domain('parent_state', 'in', states)
        if form.get('journal_ids'):
            domain &= Domain('journal_id', 'in', form['journal_ids'])
        return domain

    @api.model
    def _classify(self, account):
        """ :return: (section, line) of the statement for the cash paid or received against `account` """
        activity, line = TYPE_FLOWS.get(account.account_type, ('operating', 'other'))
        return account.cash_flow_activity or activity, line

    @api.model
    def _allocate(self, move_line, amount, transit_accounts, flows, depth=0):
        """ Add `amount` of cash to the flows of what `move_line` stands for. A line on a transit account
        (e.g. outstanding receipts) stands for the lines it is reconciled with, in proportion. """
        account = move_line.account_id
        if account.account_type == 'asset_cash':
            flows[('operating', 'transfer', False)] += amount
            return
        if account in transit_accounts and depth < MAX_TRANSIT_DEPTH:
            total = abs(move_line.balance)
            matched_share = 0.0
            for partial in (move_line.matched_debit_ids | move_line.matched_credit_ids) if total else []:
                counterpart = partial.debit_move_id if partial.credit_move_id == move_line else partial.credit_move_id
                if not counterpart.balance:
                    continue
                share = partial.amount / total
                matched_share += share
                for other in counterpart.move_id.line_ids - counterpart:
                    if other.account_id and other.balance:
                        self._allocate(other, amount * share * other.balance / -counterpart.balance,
                                       transit_accounts, flows, depth + 1)
            if matched_share < 1.0:
                flows[('operating', 'unmatched', False)] += amount * (1.0 - matched_share)
            return
        activity, line = self._classify(account)
        flows[(activity, line, account.id)] += amount

    @api.model
    def _get_cash_flow(self, form):
        """ :return: dictionary with the opening, closing and net change of the cash and the sections of the
                     statement: list of {activity, name, lines: [{key, name, amount, accounts}], total} """
        company_id = form['company_id'][0] if isinstance(form['company_id'], (list, tuple)) else form['company_id']
        company = self.env['res.company'].browse(company_id)
        currency = company.currency_id
        date_from, date_to = form['date_from'], form['date_to']
        if not date_from or not date_to:
            raise UserError(_('Set the start and end dates of the cash flow statement.'))
        MoveLine = self.env['account.move.line']
        cash_domain = self._get_line_domain(form, company) & Domain('account_id.account_type', '=', 'asset_cash')

        [(opening,)] = MoveLine._read_group(cash_domain & Domain('date', '<', date_from), aggregates=['balance:sum'])
        cash_lines = MoveLine.search(cash_domain & Domain('date', '>=', date_from) & Domain('date', '<=', date_to))
        net_change = sum(cash_lines.mapped('balance'))

        transit_accounts = self._get_transit_accounts(company)
        flows = defaultdict(float)
        for move in cash_lines.move_id:
            for move_line in move.line_ids:
                if move_line.account_id and move_line.account_id.account_type != 'asset_cash' and move_line.balance:
                    self._allocate(move_line, -move_line.balance, transit_accounts, flows)

        labels = self._get_line_labels()
        Account = self.env['account.account']
        sections = []
        for activity, activity_name in Account._fields['cash_flow_activity']._description_selection(self.env):
            lines = []
            for line_key in LINE_ORDER:
                keys = [key for key in flows if key[:2] == (activity, line_key)]
                if not keys:
                    continue
                line_accounts = sorted((
                    {'code': account.code or '', 'name': account.name, 'amount': currency.round(flows[key])}
                    for key in keys if key[2]
                    for account in [Account.browse(key[2])]
                ), key=lambda values: values['code'])
                amount = currency.round(sum(flows[key] for key in keys))
                if currency.is_zero(amount) and all(currency.is_zero(values['amount']) for values in line_accounts):
                    continue
                lines.append({'key': line_key, 'name': labels[line_key], 'amount': amount, 'accounts': line_accounts})
            sections.append({
                'activity': activity,
                'name': activity_name,
                'lines': lines,
                'total': currency.round(sum(line['amount'] for line in lines)),
            })

        # the flows are shares of the cash lines: the rounding of the shares is left in the largest line
        difference = currency.round(net_change - sum(section['total'] for section in sections))
        if not currency.is_zero(difference):
            section = max(sections, key=lambda s: max((abs(line['amount']) for line in s['lines']), default=0.0))
            if section['lines']:
                line = max(section['lines'], key=lambda line: abs(line['amount']))
                line['amount'] = currency.round(line['amount'] + difference)
                section['total'] = currency.round(section['total'] + difference)

        return {
            'sections': sections,
            'opening': currency.round(opening),
            'net_change': currency.round(net_change),
            'closing': currency.round(opening + net_change),
            'currency': currency,
            'company': company,
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the reconciliations are read through the ORM, the totals with a grouped query: write the changes first
        self.env.flush_all()
        form = data['form']
        cash_flow = self._get_cash_flow(form)
        journals = self.env['account.journal'].browse(form.get('journal_ids') or [])
        return {
            'doc_ids': docids,
            'doc_model': 'account.cash.flow.report',
            'data': form,
            'docs': self.env['account.cash.flow.report'].browse(docids),
            'time': time,
            'print_journal': journals.mapped('code'),
            'cash_flow': cash_flow,
        }
