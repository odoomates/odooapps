from collections import defaultdict

from odoo import api, fields, models

EMPTY = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}


class OmDynamicReportFinancial(models.AbstractModel):
    _inherit = 'om.dynamic.report.financial'

    # the statements a budget can be shown on: the flows of a period
    _odr_budget = False

    @api.model
    def _om_filters(self):
        filters = super()._om_filters()
        if self._odr_budget:
            filters.append({'key': 'budget_ids', 'label': self.env._("Budgets"), 'model': 'account.budget',
                            'icon': 'savings', 'domain': [['state', 'not in', ['draft', 'cancel']]]})
        return filters

    @api.model
    def _odr_budget_shown(self, options):
        """Whether the budget columns are shown: budgets chosen, and no other split of the columns."""
        return bool(self._odr_budget and options.get('budget_ids') and not self._odr_split_columns(options))

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        if not self._odr_budget_shown(options):
            return columns
        index = next((i for i, column in enumerate(columns) if column['key'] == 'balance'), len(columns) - 1)
        columns[index + 1:index + 1] = [
            {'key': 'budget', 'label': self.env._("Budget"), 'type': 'monetary', 'optional': False,
             'help': self.env._("What the budgets chosen plan for the period.")},
            {'key': 'budget_achievement', 'label': self.env._("Achievement %"), 'type': 'percent',
             'help': self.env._("The balance of the period, as a percentage of the budget.")},
        ]
        return columns

    @api.model
    def _odr_extra_columns(self, options, index, period, account_sums):
        columns = super()._odr_extra_columns(options, index, period, account_sums)
        if index == 0 and self._odr_budget_shown(options):
            columns['budget'] = self._odr_budget_sums(options, period, account_sums)
        return columns

    @api.model
    def _odr_values(self, amounts_by_period, sign, options, account_id=False):
        values = super()._odr_values(amounts_by_period, sign, options, account_id)
        if 'budget' in values:
            budget = values['budget']
            values['budget_achievement'] = values['balance'] / budget * 100 if budget else False
        return values

    @api.model
    def _odr_budget_planned(self, line, date_from, date_to):
        """What a budget line plans for the period: its amount at its planned date, or the share of the days of
        the period in its own period."""
        if line.distribution == 'at_date':
            planned_date = line.planned_date or line.date_to
            return line.planned_amount if date_from <= planned_date <= date_to else 0.0
        start, end = max(line.date_from, date_from), min(line.date_to, date_to)
        if start > end:
            return 0.0
        return line.planned_amount * ((end - start).days + 1) / ((line.date_to - line.date_from).days + 1)

    @api.model
    def _odr_budget_sums(self, options, period, account_sums):
        """{account id: {'debit', 'credit', 'balance'}} of what the budgets plan for the period, as balances: a
        cost as a debit, an income as a credit. A budgetary position of several accounts is spread over them in
        proportion to what they booked in the period, or evenly when they booked nothing."""
        date_to = fields.Date.to_date(period['date_to'])
        date_from = fields.Date.to_date(period['date_from']) if period.get('date_from') \
            else self._odr_fiscal_year_start(date_to)
        lines = self.env['account.budget'].browse(options['budget_ids']).exists().line_ids.filtered(
            lambda line: line.position_id.account_ids and line.date_from <= date_to and line.date_to >= date_from)
        result = defaultdict(lambda: dict(EMPTY))
        for line in lines:
            planned = self._odr_budget_planned(line, date_from, date_to)
            if not planned:
                continue
            balance = planned if line.budget_type == 'expense' else -planned
            accounts = line.position_id.account_ids
            booked = {account.id: abs(account_sums.get(account.id, EMPTY)['balance']) for account in accounts}
            total = sum(booked.values())
            for account in accounts:
                share = booked[account.id] / total if total else 1.0 / len(accounts)
                result[account.id]['balance'] += balance * share
        return dict(result)


class OmDynamicReportProfitLoss(models.AbstractModel):
    _inherit = 'om.dynamic.report.profit.loss'

    _odr_budget = True
