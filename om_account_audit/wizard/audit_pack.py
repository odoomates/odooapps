from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountAuditPack(models.TransientModel):
    _name = 'account.audit.pack'
    _description = 'Audit Pack'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Start Date', required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string='End Date', required=True,
                          default=lambda self: fields.Date.context_today(self).replace(day=1) - relativedelta(days=1))
    run_check = fields.Boolean(string='Run an Integrity Check', default=True,
                               help='Check the data inalterability now, and print its result. Otherwise the last '
                                    'check is printed.')

    @api.model
    def _default_date_from(self):
        return fields.Date.context_today(self).replace(day=1) - relativedelta(months=1)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for pack in self:
            if pack.date_from > pack.date_to:
                raise UserError(self.env._('The start date is after the end date.'))

    def action_print(self):
        self.ensure_one()
        if self.run_check:
            self.env['account.integrity.check']._run(self.company_id)
        return self.env.ref('om_account_audit.action_report_audit_pack').report_action(self)
