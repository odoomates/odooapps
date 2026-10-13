from odoo import models, fields, api, SUPERUSER_ID, _
from odoo.exceptions import UserError


class ChangeLockDate(models.TransientModel):
    _name = 'change.lock.date'
    _description = 'Change Lock Date'

    @api.model
    def default_get(self, vals):
        res = super().default_get(vals)
        company_rec = self.env.company
        res.update({
            'company_id': company_rec.id,
            'period_lock_date': company_rec.period_lock_date,
            'fiscalyear_lock_date': company_rec.fiscalyear_lock_date,
            'tax_lock_date': company_rec.tax_lock_date,
        })
        return res

    company_id = fields.Many2one(
        'res.company', string="Company",
        required=True, default=lambda self: self.env.company
    )
    tax_lock_date = fields.Date(
        string="Tax Return Lock Date",
        help="No users can edit journal entries related to a tax prior and inclusive of this date.")
    period_lock_date = fields.Date(
        string='Journal Entries Lock Date',
        help='Prevent posting of journal entries in this period.'
    )
    fiscalyear_lock_date = fields.Date(
        string='Lock Date for All Users',
        default=lambda self: self.env.company.fiscalyear_lock_date,
        help='No users, including Advisers, can edit accounts prior to and inclusive of '
             'this date. Use it for fiscal year locking.'
    )

    def update_lock_date(self):
        self.ensure_one()
        has_manager_group = self.env.user.has_group('account.group_account_manager')
        if not (has_manager_group or self.env.uid == SUPERUSER_ID):
            raise UserError(_("You Are Not Allowed To Perform This Operation"))
        if self.env.uid != SUPERUSER_ID and self.company_id not in self.env.user.company_ids:
            raise UserError(_("You cannot change the lock dates of another company."))
        # sudo() is required because setting lock dates writes on res.company,
        # which accounting managers are not allowed to write on.
        self.company_id.sudo().write({
            'period_lock_date': self.period_lock_date,
            'fiscalyear_lock_date': self.fiscalyear_lock_date,
            'tax_lock_date': self.tax_lock_date,
        })
