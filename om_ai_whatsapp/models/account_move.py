from odoo import models
from odoo.exceptions import AccessError
from odoo.tools.misc import formatLang


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        """ The WhatsApp assistant never posts an entry. """
        if not self.env.su and self.env.user.om_ai_whatsapp_assistant:
            raise AccessError(self.env._('The WhatsApp assistant cannot post invoices.'))
        return super().action_post()

    def _om_ai_whatsapp_amount(self, amount):
        self.ensure_one()
        return formatLang(self.env, amount, currency_obj=self.currency_id)
