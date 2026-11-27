from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_ai_whatsapp_assistant = fields.Boolean(
        'WhatsApp Assistant', readonly=True, copy=False,
        help="The user the WhatsApp AI assistant of the company works as. It has no password: nobody logs in "
             "with it.")

    def _om_ai_ensure_chat(self):
        # the assistant user needs no AI chat in Discuss
        return super(ResUsers, self.filtered(lambda user: not user.om_ai_whatsapp_assistant))._om_ai_ensure_chat()
