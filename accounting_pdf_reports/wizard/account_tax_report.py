from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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

    report_kind = fields.Selection(
        [('tax', 'By Tax'), ('grid', 'By Tax Grid')], string='Report', default='tax', required=True,
        help="By Tax Grid prints the tax return of the country as its localization lays it out, grid by grid.")
    tax_grid_report_id = fields.Many2one(
        'account.report', string='Tax Return', default=lambda self: self._default_tax_grid_report(),
        domain=lambda self: self._tax_grid_report_domain())

    def _tax_grid_report_domain(self):
        # the tax returns of the localizations, not the sections of one
        generic = self.env.ref('account.generic_tax_report', raise_if_not_found=False)
        return [('root_report_id', '=', generic.id if generic else False), ('country_id', '!=', False),
                ('section_main_report_ids', '=', False)]

    def _default_tax_grid_report(self):
        country = self.env.company.account_fiscal_country_id
        return self.env['account.report'].search(
            self._tax_grid_report_domain() + [('country_id', '=', country.id)], order='sequence, id', limit=1)

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
        if self.report_kind == 'grid':
            if not self.tax_grid_report_id:
                raise UserError(_("Pick the tax return to print. The tax returns come with the fiscal localization "
                                  "of the country (the l10n modules)."))
            data['form']['tax_grid_report_id'] = self.tax_grid_report_id.id
            return self.env.ref('accounting_pdf_reports.action_report_account_tax_grid').report_action(self, data=data)
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
