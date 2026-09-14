from dateutil.relativedelta import relativedelta

from odoo import fields, models


class PayslipLinesContributionRegister(models.TransientModel):
    _name = 'payslip.lines.contribution.register'
    _description = 'Payslip Lines by Contribution Registers'

    date_from = fields.Date(string='Date From', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='Date To', required=True,
        default=lambda self: fields.Date.context_today(self) + relativedelta(day=31))

    def print_report(self):
        active_ids = self.env.context.get('active_ids', [])
        datas = {
             'ids': active_ids,
             'model': 'hr.contribution.register',
             'form': self.read()[0]
        }
        return self.env.ref('om_hr_payroll.action_contribution_register').report_action([], data=datas)
