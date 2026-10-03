# Refuses Send message from the chatter when a profile hides it; Log note
# (the note subtype) stays allowed.
from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.mail.controllers.thread import ThreadController

NOTE_SUBTYPE = 'mail.mt_note'


class ThreadAccess(ThreadController):

    @http.route()
    def mail_message_post(self, thread_model, thread_id, post_data, context=None, **kwargs):
        post_data = post_data or {}
        # a note that names partners notifies them: it is a message too
        sends = post_data.get('subtype_xmlid') != NOTE_SUBTYPE or post_data.get('partner_ids')
        if request.env.uid and sends:
            rules = request.env['om.access.profile']._current_rules()
            if rules.enabled and rules.model_flag(thread_model, 'hide_send_message'):
                raise AccessError(_("Your access profile does not allow sending messages here. "
                                    "Log a note instead."))
        return super().mail_message_post(thread_model, thread_id, post_data, context=context, **kwargs)
