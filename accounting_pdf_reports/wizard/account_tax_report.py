from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

PERIODS = [
    ('this_month', 'This Month'),
    ('this_quarter', 'This Quarter'),
    ('this_year', 'This Fiscal Year'),
    ('last_month', 'Last Month'),
    ('last_quarter', 'Last Quarter'),
    ('last_year', 'Last Fiscal Year'),
    ('custom', 'Custom'),
]


class AccountTaxReport(models.TransientModel):
    _name = 'account.tax.report.wizard'
    _inherit = "account.common.report"
    _description = 'Tax Report'

    period = fields.Selection(PERIODS, string='Period', default='this_month', required=True)
    date_from = fields.Date(
        string='Date From', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1)
    )
    date_to = fields.Date(
        string='Date To', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1) + relativedelta(months=1, days=-1)
    )

    def _period_dates(self, period):
        """ :return: (first day, last day) of the period, the years being the fiscal years of the company """
        today = fields.Date.context_today(self)
        company = self.company_id or self.env.company
        if period in ('this_month', 'last_month'):
            start = today.replace(day=1) - relativedelta(months=1 if period == 'last_month' else 0)
            return start, start + relativedelta(months=1, days=-1)
        if period in ('this_quarter', 'last_quarter'):
            start = today.replace(day=1, month=(today.month - 1) // 3 * 3 + 1)
            start -= relativedelta(months=3 if period == 'last_quarter' else 0)
            return start, start + relativedelta(months=3, days=-1)
        if period in ('this_year', 'last_year'):
            day = today - relativedelta(years=1) if period == 'last_year' else today
            dates = company.compute_fiscalyear_dates(day)
            return dates['date_from'], dates['date_to']
        return self.date_from, self.date_to

    @api.onchange('period')
    def _onchange_period(self):
        if self.period and self.period != 'custom':
            self.date_from, self.date_to = self._period_dates(self.period)

    def _print_report(self, data):
        return self.env.ref('accounting_pdf_reports.action_report_account_tax').report_action(self, data=data)

    def action_open_tax_closing(self):
        """ Close the period of the report: the tax due on it goes to the tax payable or receivable account """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Close Tax Period'),
            'res_model': 'account.tax.closing.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_date_from': self.date_from,
                'default_date_to': self.date_to,
                'default_company_id': (self.company_id or self.env.company).id,
            },
        }
