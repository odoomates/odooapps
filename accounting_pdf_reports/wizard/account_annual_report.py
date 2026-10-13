from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountAnnualReport(models.TransientModel):
    _name = 'account.annual.report'
    _inherit = 'account.common.report'
    _description = 'Annual Report'

    date_from = fields.Date(string='Start Date', required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string='End Date', required=True, default=lambda self: self._default_date_to())
    journal_ids = fields.Many2many(
        'account.journal', 'account_annual_report_journal_rel', 'report_id', 'journal_id',
        string='Journals', required=True,
        # 'child_of': the journals of the company and of the branches it consolidates
        default=lambda self: self.env['account.journal'].search([('company_id', 'child_of', self.env.company.id)]),
        domain="[('company_id', 'child_of', company_id)]",
    )
    include_balance_sheet = fields.Boolean(string='Balance Sheet', default=True)
    include_profit_and_loss = fields.Boolean(string='Profit and Loss', default=True)
    include_cash_flow = fields.Boolean(
        string='Cash Flow Statement', default=False,
        help="The cash flow statement is optional: the pack is the balance sheet and the "
             "profit and loss unless you ask for it.")
    compare_previous_year = fields.Boolean(
        string='Compare with Previous Year', default=True,
        help="Print a second column holding the same period one year earlier.")
    show_variance = fields.Boolean(
        string='Show Variance', default=True,
        help="Add the movement between the two periods, in amount and per cent. "
             "Only printed when the report is compared.")
    include_key_figures = fields.Boolean(
        string='Key Figures', default=True,
        help="A summary page: revenue, expenses, the result, total assets and cash.")
    notes = fields.Text(
        string='Notes',
        help="Printed at the end of the report, under Notes to the Financial Statements.")
    include_signatures = fields.Boolean(
        string='Approval Page', default=False,
        help="A page to sign: prepared by, reviewed by and approved by.")

    @api.model
    def _default_date_from(self):
        return self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_from']

    @api.model
    def _default_date_to(self):
        return self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_to']

    def _check_dates(self):
        for report in self:
            if report.date_from > report.date_to:
                raise UserError(_('The start date must be before the end date.'))

    def _check_sections(self):
        for report in self:
            if not (report.include_balance_sheet or report.include_profit_and_loss
                    or report.include_cash_flow):
                raise UserError(_('Choose at least one statement to include in the report.'))

    def _comparison(self, data):
        """ The same span of days, one year earlier.

        Shifting the chosen period is what a reader expects of a comparative column,
        and it stays right when the period is not a whole fiscal year. The context is
        the report's own with the dates swapped, so the comparison keeps the same
        journals, company and posted/all setting as the figures beside it.
        """
        date_from = self.date_from - relativedelta(years=1)
        date_to = self.date_to - relativedelta(years=1)
        context = dict(data['form'].get('used_context') or {})
        context.update({'date_from': date_from, 'date_to': date_to, 'strict_range': True})
        return {
            'enable_filter': True,
            'date_from_cmp': date_from,
            'date_to_cmp': date_to,
            'comparison_context': context,
        }

    def _print_report(self, data):
        self._check_dates()
        self._check_sections()
        data['form'].update(self.read([
            'include_balance_sheet', 'include_profit_and_loss', 'include_cash_flow',
            'compare_previous_year', 'show_variance', 'include_key_figures',
            'notes', 'include_signatures',
        ])[0])
        if self.compare_previous_year:
            data['form'].update(self._comparison(data))
        return self.env.ref('accounting_pdf_reports.action_report_annual').report_action(self, data=data)
