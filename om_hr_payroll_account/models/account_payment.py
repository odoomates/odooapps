from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payslip_ids = fields.Many2many(
        'hr.payslip', 'hr_payslip_account_payment_rel', 'payment_id', 'payslip_id', string='Payslips',
        readonly=True, copy=False, groups='om_hr_payroll.group_hr_payroll_user',
    )
