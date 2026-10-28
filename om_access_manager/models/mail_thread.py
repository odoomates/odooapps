# Blocks message_post called by a client through the API, which the chatter
# guard (controllers/mail.py) does not see. Server-side posting is left alone.
from odoo import _, models

NOTE_SUBTYPE = 'mail.mt_note'


def chatter_refusal(env, model_name, is_note):
    """ Why the profiles of the current user refuse posting on ``model_name``
    (a note, or a message to the followers), or None. """
    rules = env['om.access.profile']._current_rules()
    if not rules.enabled:
        return None
    if not is_note and rules.model_flag(model_name, 'hide_send_message'):
        return _("Your access profile does not allow sending messages here. Log a note instead.")
    if is_note and rules.model_flag(model_name, 'hide_log_note'):
        return _("Your access profile does not allow logging notes here.")
    return None


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def message_post(self, **kwargs):
        if self._om_rpc_entry('message_post'):
            # a note that names partners notifies them: it is a message too
            is_note = (kwargs.get('subtype_xmlid') in (None, NOTE_SUBTYPE)
                       and not kwargs.get('subtype_id') and not kwargs.get('partner_ids'))
            if refusal := chatter_refusal(self.env, self._name, is_note):
                raise self.env['om.access.profile']._om_refusal(
                    refusal, model=self._name, method='message_post', record_ids=self.ids)
        return super().message_post(**kwargs)
