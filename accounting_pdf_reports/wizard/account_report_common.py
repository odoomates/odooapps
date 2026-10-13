from odoo import fields, models


class AccountCommonReport(models.TransientModel):
    _inherit = "account.common.report"

    # the journals of the current company: the default of the account module looks for those of the
    # company of the wizard, which is not set yet when the default is computed
    journal_ids = fields.Many2many(
        default=lambda self: self.env['account.journal'].search([('company_id', '=', self.env.company.id)]),
    )
