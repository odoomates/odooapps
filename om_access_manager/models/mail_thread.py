# Blocks message_post called by a client through the API, which the chatter
# guard (controllers/mail.py) does not see. Server-side posting is left alone.
from odoo import _, models
from odoo.exceptions import AccessError

NOTE_SUBTYPE = 'mail.mt_note'


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def message_post(self, **kwargs):
        if self._om_rpc_entry('message_post'):
            sends = (kwargs.get('subtype_xmlid') not in (None, NOTE_SUBTYPE)
                     or kwargs.get('subtype_id') or kwargs.get('partner_ids'))
            rules = self.env['om.access.profile']._current_rules()
            if sends and rules.enabled and rules.model_flag(self._name, 'hide_send_message'):
                raise AccessError(_("Your access profile does not allow sending messages here. "
                                    "Log a note instead."))
        return super().message_post(**kwargs)
