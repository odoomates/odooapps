from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    om_release_warning = fields.Text(compute='_compute_om_release_warning')
    om_release_blocked = fields.Boolean(compute='_compute_om_release_warning')

    @api.depends('line_ids')
    def _compute_om_release_warning(self):
        for wizard in self:
            bills = wizard.line_ids.move_id._om_not_released()
            wizard.om_release_blocked = bool(bills._om_not_released(policies=('block',)))
            wizard.om_release_warning = ', '.join(bills.mapped('display_name')) if bills else False

    def _create_payments(self):
        self.line_ids.move_id._om_check_payment_allowed()
        return super()._create_payments()
