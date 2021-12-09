from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        if self.move_type == 'out_invoice' and self.partner_id and \
                self.partner_id.amount_credit_limit != 0 and not self._context.get('skip_credit_check'):
            amount_due = self.partner_id.credit - self.partner_id.debit + self.amount_total
            if amount_due > self.partner_id.amount_credit_limit:
                return {
                    'name': _('Warning'),
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'warning.warning',
                    'target': 'new',
                    'context': {},
                }
        return super(AccountMove, self).action_post()


