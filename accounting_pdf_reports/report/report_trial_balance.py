import time
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ReportTrialBalance(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_trialbalance'
    _description = 'Trial Balance Report'

    def _get_balances(self, accounts, context):
        """ :return: {account id: balance} of the entries the context selects """
        if not accounts:
            return {}
        tables, where_clause, where_params = self.env['account.move.line'].with_context(context)._query_get()
        tables = tables.replace('"', '') or 'account_move_line'
        filters = " AND " + where_clause.strip() if where_clause.strip() else ""
        self.env.cr.execute(
            "SELECT account_id AS id, SUM(debit) - SUM(credit) AS balance FROM " + tables
            + " WHERE account_id IN %s" + filters + " GROUP BY account_id",
            (tuple(accounts.ids),) + tuple(where_params))
        return {row['id']: row['balance'] for row in self.env.cr.dictfetchall()}

    def _get_fiscal_year_start(self, date_from):
        company = self.env['res.company'].browse(self.env.context.get('company_id')) or self.env.company
        return company.compute_fiscalyear_dates(date_from)['date_from']

    def _get_initial_balances(self, accounts):
        """ The balance of each account before the start date of the report: its whole history for the balance
        sheet accounts, since the start of the fiscal year for the income and expense accounts (they start again
        at zero every year).

        :return: {account id: balance}, empty without a start date (the report then covers the whole history)
        """
        date_from = self.env.context.get('date_from')
        if not date_from or not accounts:
            return {}
        date_from = fields.Date.to_date(date_from)
        fiscal_year_start = self._get_fiscal_year_start(date_from)
        brought_forward = accounts.filtered('include_initial_balance')
        balances = self._get_balances(
            brought_forward, dict(self.env.context, date_to=False, strict_range=True, initial_bal=True))
        if fiscal_year_start < date_from:
            balances.update(self._get_balances(accounts - brought_forward, dict(
                self.env.context, date_from=fiscal_year_start, date_to=date_from - timedelta(days=1),
                strict_range=True, initial_bal=False)))
        return balances

    def _get_undistributed_result(self, accounts):
        """ The income and expense of the fiscal years before the one of the start date. No account carries it
        forward, but it is still part of the balance of the company: without it the report does not add up to
        zero.

        :return: the balance, 0.0 without a start date (the accounts then show their whole history)
        """
        date_from = self.env.context.get('date_from')
        if not date_from:
            return 0.0
        fiscal_year_start = self._get_fiscal_year_start(fields.Date.to_date(date_from))
        return sum(self._get_balances(accounts.filtered(lambda account: not account.include_initial_balance), dict(
            self.env.context, date_from=fiscal_year_start, date_to=False, strict_range=True,
            initial_bal=True)).values())

    def _get_accounts(self, accounts, display_account):
        """ compute the balance, debit and credit for the provided accounts
            :Arguments:
                `accounts`: list of accounts record,
                `display_account`: it's used to display either all accounts or those accounts which balance is > 0
            :Returns a list of dictionary of Accounts with following key and value
                `name`: Account name,
                `code`: Account code,
                `initial_balance`: the balance before the start date (0.0 without a start date),
                `credit`: total amount of credit of the period,
                `debit`: total amount of debit of the period,
                `balance`: the balance at the end of the period, the initial balance included,
        """

        account_result = {}
        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = self.env['account.move.line']._query_get()
        tables = tables.replace('"','')
        if not tables:
            tables = 'account_move_line'
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        # compute the balance, debit and credit for the provided accounts
        request = ("SELECT account_id AS id, SUM(debit) AS debit, SUM(credit) AS credit, "
                   "(SUM(debit) - SUM(credit)) AS balance" +\
                   " FROM " + tables + " WHERE account_id IN %s " + filters + " GROUP BY account_id")
        params = (tuple(accounts.ids),) + tuple(where_params)
        self.env.cr.execute(request, params)
        for row in self.env.cr.dictfetchall():
            account_result[row.pop('id')] = row

        initial_balances = self._get_initial_balances(accounts)
        has_start_date = bool(self.env.context.get('date_from'))
        account_res = []
        for account in accounts:
            res = dict((fn, 0.0) for fn in ['credit', 'debit', 'balance'])
            res['initial_balance'] = initial_balances.get(account.id, 0.0)
            res['balance'] = res['initial_balance']
            currency = account.currency_id and account.currency_id or self.env.company.currency_id
            res['code'] = account.code
            res['name'] = account.name
            if account.id in account_result:
                res['debit'] = account_result[account.id].get('debit')
                res['credit'] = account_result[account.id].get('credit')
                res['balance'] += account_result[account.id].get('balance')
            # with a start date, an account left out would leave the columns unbalanced: the filters only drop
            # the accounts with nothing to show
            if has_start_date and any(not currency.is_zero(res[fn]) for fn in ('initial_balance', 'debit', 'credit', 'balance')):
                account_res.append(res)
                continue
            if display_account == 'all':
                account_res.append(res)
            if display_account == 'not_zero' and not currency.is_zero(res['balance']):
                account_res.append(res)
            if display_account == 'movement' and (
                    not currency.is_zero(res['debit']) or not currency.is_zero(res['credit'])):
                account_res.append(res)
        undistributed = self._get_undistributed_result(accounts)
        if not self.env.company.currency_id.is_zero(undistributed):
            account_res.append({
                'code': '',
                'name': _('Result Brought Forward'),
                'initial_balance': undistributed,
                'debit': 0.0,
                'credit': 0.0,
                'balance': undistributed,
            })
        return account_res

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not self.env.context.get('active_model'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_ids', []))
        display_account = data['form'].get('display_account')
        accounts = docs if model == 'account.account' else self.env['account.account'].search([])
        context = data['form'].get('used_context')
        analytic_accounts = []
        if data['form'].get('analytic_account_ids'):
            analytic_account_ids = self.env['account.analytic.account'].browse(data['form'].get('analytic_account_ids'))
            context['analytic_account_ids'] = analytic_account_ids
            analytic_accounts = [account.name for account in analytic_account_ids]
        account_res = self.with_context(context)._get_accounts(accounts, display_account)
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search(
                         [('id', 'in', data['form']['journal_ids'])])]
        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'print_journal': codes,
            'analytic_accounts': analytic_accounts,
            'time': time,
            'Accounts': account_res,
        }
