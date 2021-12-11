from odoo import models, fields, _


class RaiseWarning(models.TransientModel):
    _name = "warning.warning"
    _description = "Warning"

    def action_confirm(self):
        invoice = self.env['account.move'].browse(self._context.get('active_id'))
        if invoice.exists():
            return invoice.with_context(skip_credit_check=True).action_post()
