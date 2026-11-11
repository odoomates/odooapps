from odoo import fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    om_journal_type = fields.Selection(related='journal_id.type')
    om_create_batch = fields.Boolean(
        string='Create a Batch', help="Puts the payments in a new batch, to send them to the bank in one file.")
    om_batch_id = fields.Many2one('account.batch.payment', readonly=True)

    def _create_payments(self):
        payments = super()._create_payments()
        if self.om_create_batch and self.om_journal_type == 'bank' and payments:
            action = payments.action_create_batch_payment()
            self.om_batch_id = action['res_id']
        return payments

    def action_create_payments(self):
        action = super().action_create_payments()
        if self.om_batch_id and isinstance(action, dict):
            return {
                'name': self.om_batch_id.name,
                'type': 'ir.actions.act_window',
                'res_model': 'account.batch.payment',
                'res_id': self.om_batch_id.id,
                'views': [(False, 'form')],
            }
        return action
