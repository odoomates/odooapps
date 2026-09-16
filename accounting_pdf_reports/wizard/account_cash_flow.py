from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountCashFlowReport(models.TransientModel):
    _name = 'account.cash.flow.report'
    _inherit = 'account.common.report'
    _description = 'Cash Flow Statement'

    date_from = fields.Date(string='Start Date', required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string='End Date', required=True, default=lambda self: self._default_date_to())
    journal_ids = fields.Many2many(
        'account.journal', 'account_cash_flow_report_journal_rel', 'report_id', 'journal_id',
        string='Journals', required=True,
        default=lambda self: self.env['account.journal'].search([('company_id', '=', self.env.company.id)]),
        domain="[('company_id', '=', company_id)]",
    )
    display_detail = fields.Selection(
        [('summary', 'Summary'), ('accounts', 'Detail by Account')],
        string='Display', required=True, default='summary',
    )

    @api.model
    def _default_date_from(self):
        return self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_from']

    @api.model
    def _default_date_to(self):
        return fields.Date.context_today(self)

    def _check_dates(self):
        for report in self:
            if report.date_from > report.date_to:
                raise UserError(_('The start date must be before the end date.'))

    def _print_report(self, data):
        self._check_dates()
        data['form'].update(self.read(['display_detail'])[0])
        return self.env.ref('accounting_pdf_reports.action_report_cash_flow').report_action(self, data=data)
