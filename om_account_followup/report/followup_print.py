from odoo import api, fields, models
from odoo.tools import format_date


class ReportCustomerStatement(models.AbstractModel):
    _name = 'report.om_account_followup.report_customer_statement'
    _description = 'Customer Statement'

    @api.model
    def _get_report_values(self, docids, data=None):
        partners = self.env['res.partner'].browse(docids).commercial_partner_id
        today = fields.Date.context_today(self)
        company = self.env.company
        bank_accounts = company.partner_id.bank_ids
        return {
            'doc_ids': partners.ids,
            'doc_model': 'res.partner',
            'docs': partners,
            'company': company,
            'today': today,
            'today_label': format_date(self.env, today),
            'bank_accounts': bank_accounts,
            'statement': lambda partner: partner.with_company(company)._followup_statement_lines(today),
            'level_text': lambda partner: partner.with_company(company)._followup_level_text(today),
            'format_date': lambda value: format_date(self.env, value),
        }
