from collections import defaultdict

from odoo import api, fields, models, _
from odoo.fields import Domain

RECEIPT_ROWS = ('customers', 'recurring_in', 'expected_in', 'transit_in', 'bank_in')
PAYMENT_ROWS = ('suppliers', 'recurring_out', 'expected_out', 'transit_out', 'bank_out')


class ReportCashForecast(models.AbstractModel):
    _name = 'report.om_account_cash_forecast.report_cash_forecast'
    _description = 'Cash Forecast Report'

    @api.model
    def _get_row_labels(self):
        return {
            'customers': _('Customer invoices'),
            'recurring_in': _('Recurring receipts'),
            'expected_in': _('Other expected receipts'),
            'transit_in': _('Receipts not yet in the bank'),
            'bank_in': _('Bank receipts already recorded'),
            'suppliers': _('Vendor bills'),
            'recurring_out': _('Recurring payments'),
            'expected_out': _('Other expected payments'),
            'transit_out': _('Payments not yet out of the bank'),
            'bank_out': _('Bank payments already recorded'),
        }

    @api.model
    def _get_transit_accounts(self, company):
        journals = self.env['account.journal'].sudo().search([('company_id', 'child_of', company.id)])
        method_lines = self.env['account.payment.method.line'].sudo().search([('journal_id', 'in', journals.ids)])
        return method_lines.payment_account_id.filtered(
            lambda account: account.account_type != 'asset_cash').sudo(False)

    def _get_forecast_items(self, wizard, date_to):
        """ The receipts (positive) and payments (negative) expected up to `date_to`, in company currency.
        Other modules add theirs.

        :return: list of dictionaries with `date`, `amount`, `row` and `partner` (a name)
        """
        company = wizard.company_id
        currency = company.currency_id
        MoveLine = self.env['account.move.line']
        items = []
        company_domain = Domain('company_id', 'child_of', company.id)

        # open invoices and bills, on their due date
        states = ('posted', 'draft') if wizard.include_drafts else ('posted',)
        partner_lines = MoveLine.search(
            company_domain
            & Domain('account_id.account_type', 'in', ('asset_receivable', 'liability_payable'))
            & Domain('parent_state', 'in', states)
            & Domain('reconciled', '=', False)
            & Domain('display_type', '=', 'payment_term')
        )
        partner_lines |= MoveLine.search(
            company_domain
            & Domain('account_id.account_type', 'in', ('asset_receivable', 'liability_payable'))
            & Domain('parent_state', '=', 'posted')
            & Domain('reconciled', '=', False)
            & Domain('display_type', '!=', 'payment_term')
        )
        for line in partner_lines:
            amount = line.amount_residual if line.parent_state == 'posted' else line.balance
            if currency.is_zero(amount):
                continue
            items.append({
                'date': line.date_maturity or line.date,
                'amount': amount,
                'row': 'customers' if line.account_id.account_type == 'asset_receivable' else 'suppliers',
                'partner': line.partner_id.commercial_partner_id.name or _('No partner'),
            })

        # payments registered but not in the bank yet
        transit_accounts = self._get_transit_accounts(company)
        if transit_accounts:
            for line in MoveLine.search(company_domain & Domain('account_id', 'in', transit_accounts.ids)
                                        & Domain('parent_state', '=', 'posted') & Domain('reconciled', '=', False)):
                if not currency.is_zero(line.amount_residual):
                    items.append({
                        'date': line.date,
                        'amount': line.amount_residual,
                        'row': 'transit_in' if line.amount_residual > 0 else 'transit_out',
                        'partner': line.partner_id.commercial_partner_id.name or _('No partner'),
                    })

        # bank and cash entries already recorded with a date in the forecast
        for line in MoveLine.search(company_domain & Domain('account_id.account_type', '=', 'asset_cash')
                                    & Domain('parent_state', '=', 'posted') & Domain('date', '>=', wizard.date_from)
                                    & Domain('date', '<=', date_to)):
            if not currency.is_zero(line.balance):
                items.append({
                    'date': line.date,
                    'amount': line.balance,
                    'row': 'bank_in' if line.balance > 0 else 'bank_out',
                    'partner': line.partner_id.commercial_partner_id.name or _('No partner'),
                })

        # the payments of the recurring payments module, when it is installed
        if 'recurring.payment.line' in self.env:
            for line in self.env['recurring.payment.line'].search([
                ('company_id', 'child_of', company.id), ('state', '=', 'draft'), ('date', '<=', date_to),
            ]):
                amount = line.currency_id._convert(line.amount, currency, company, wizard.date_from)
                inbound = line.recurring_payment_id.payment_type == 'inbound'
                items.append({
                    'date': line.date,
                    'amount': amount if inbound else -amount,
                    'row': 'recurring_in' if inbound else 'recurring_out',
                    'partner': line.partner_id.commercial_partner_id.name or _('No partner'),
                })

        # the items entered by hand
        for item in self.env['account.cash.forecast.item'].search([('company_id', 'child_of', company.id)]):
            amount = item.currency_id._convert(item.amount, currency, company, wizard.date_from)
            for date in item._get_occurrences(wizard.date_from, date_to):
                items.append({
                    'date': date,
                    'amount': amount if item.direction == 'in' else -amount,
                    'row': 'expected_in' if item.direction == 'in' else 'expected_out',
                    'partner': item.partner_id.commercial_partner_id.name or item.name,
                })
        return items

    @api.model
    def _get_forecast(self, wizard):
        """ :return: dictionary with `columns` (labels), `opening` and `closing` (per column), `sections`
                     (receipts and payments, each with rows {key, name, amounts, total, partners}) and `net` """
        wizard.ensure_one()
        company = wizard.company_id
        currency = company.currency_id
        periods = wizard._get_periods()
        date_to = periods[-1][1]
        with_overdue = wizard.overdue == 'include'
        columns = ([_('Overdue')] if with_overdue else []) + [label for _start, _end, label in periods]
        offset = 1 if with_overdue else 0

        def column_of(date):
            if date < wizard.date_from:
                return 0 if with_overdue else None
            for index, (start, end, _label) in enumerate(periods):
                if start <= date <= end:
                    return index + offset
            return None

        amounts = defaultdict(lambda: [0.0] * len(columns))
        partners = defaultdict(lambda: defaultdict(lambda: [0.0] * len(columns)))
        for item in self._get_forecast_items(wizard, date_to):
            column = column_of(item['date'])
            if column is None:
                continue
            amounts[item['row']][column] += item['amount']
            partners[item['row']][item['partner']][column] += item['amount']

        [(opening,)] = self.env['account.move.line']._read_group(
            [('company_id', 'child_of', company.id), ('account_id.account_type', '=', 'asset_cash'),
             ('parent_state', '=', 'posted'), ('date', '<', wizard.date_from)],
            aggregates=['balance:sum'])
        opening = currency.round(opening)

        labels = self._get_row_labels()
        sections = []
        for key, name, row_keys in (('receipts', _('Receipts'), RECEIPT_ROWS),
                                    ('payments', _('Payments'), PAYMENT_ROWS)):
            rows = []
            for row_key in row_keys:
                if row_key not in amounts:
                    continue
                row_amounts = [currency.round(amount) for amount in amounts[row_key]]
                if all(currency.is_zero(amount) for amount in row_amounts):
                    continue
                row_partners = sorted((
                    {'name': partner, 'amounts': [currency.round(amount) for amount in partner_amounts],
                     'total': currency.round(sum(partner_amounts))}
                    for partner, partner_amounts in partners[row_key].items()
                    if not currency.is_zero(sum(abs(amount) for amount in partner_amounts))
                ), key=lambda values: -abs(values['total']))
                rows.append({'key': row_key, 'name': labels[row_key], 'amounts': row_amounts,
                             'total': currency.round(sum(row_amounts)), 'partners': row_partners})
            totals = [currency.round(sum(row['amounts'][index] for row in rows)) for index in range(len(columns))]
            sections.append({'key': key, 'name': name, 'rows': rows, 'totals': totals,
                             'total': currency.round(sum(totals))})

        net = [currency.round(sum(section['totals'][index] for section in sections)) for index in range(len(columns))]
        openings, closings = [], []
        balance = opening
        for amount in net:
            openings.append(balance)
            balance = currency.round(balance + amount)
            closings.append(balance)
        return {
            'columns': columns,
            'sections': sections,
            'net': net,
            'net_total': currency.round(sum(net)),
            'opening': openings,
            'closing': closings,
            'currency': currency,
            'company': company,
            'lowest': min(closings) if closings else opening,
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        self.env.flush_all()
        wizards = self.env['account.cash.forecast.report'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'account.cash.forecast.report',
            'docs': wizards,
            'forecasts': {wizard.id: self._get_forecast(wizard) for wizard in wizards},
        }
