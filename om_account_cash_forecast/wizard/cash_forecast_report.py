from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountCashForecastReport(models.TransientModel):
    _name = 'account.cash.forecast.report'
    _description = 'Cash Forecast'

    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='From', required=True, default=fields.Date.context_today)
    period_type = fields.Selection([('week', 'Weeks'), ('month', 'Months')], string='By', required=True,
                                   default='month')
    period_count = fields.Integer(string='Number of Periods', required=True, default=12)
    overdue = fields.Selection(
        [('include', 'Expected now, in an Overdue column'), ('exclude', 'Left out')],
        string='Overdue Invoices and Bills', required=True, default='include',
        help="The invoices and bills already due: expected at once, or left out of the forecast.")
    include_drafts = fields.Boolean(
        string='Include Draft Invoices and Bills',
        help="The draft invoices and bills are expected on their due date like the posted ones.")
    display_partners = fields.Boolean(string='Detail by Partner')
    excel_report_available = fields.Boolean(compute='_compute_excel_report_available')

    def _compute_excel_report_available(self):
        self.excel_report_available = bool(self._get_excel_report())

    def _get_excel_report(self):
        # the Excel export comes with the Accounting Excel Reports module
        return self.env.ref('accounting_excel_reports.action_report_cash_forecast_excel', raise_if_not_found=False)

    @api.constrains('period_count')
    def _check_period_count(self):
        for report in self:
            if not 1 <= report.period_count <= 60:
                raise UserError(_('The forecast covers between 1 and 60 periods.'))

    def _get_periods(self):
        """ :return: list of (start, end, label) """
        self.ensure_one()
        periods = []
        start = self.date_from
        for index in range(self.period_count):
            if self.period_type == 'week':
                end = start + relativedelta(days=6)
                label = _('Week of %s', fields.Date.to_string(start))
            else:
                end = start + relativedelta(day=31)
                label = start.strftime('%b %Y')
            periods.append((start, end, label))
            start = end + relativedelta(days=1)
        return periods

    def action_print(self):
        self.ensure_one()
        return self.env.ref('om_account_cash_forecast.action_report_cash_forecast').report_action(self, config=False)

    def action_print_excel(self):
        self.ensure_one()
        report = self._get_excel_report()
        if not report:
            raise UserError(_('Install the Accounting Excel Reports module to export the forecast to Excel.'))
        return report.report_action(self, config=False)
