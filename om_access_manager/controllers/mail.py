# Refuses Send message or Log note from the chatter when a profile hides it.
from odoo import http
from odoo.http import request

from odoo.addons.mail.controllers.discuss import DiscussController

from ..models.mail_thread import NOTE_SUBTYPE, chatter_refusal


class ThreadAccess(DiscussController):

    @http.route()
    def mail_message_post(self, thread_model, thread_id, post_data, **kwargs):
        post_data = post_data or {}
        # a note that names partners notifies them: it is a message too
        is_note = post_data.get('subtype_xmlid') == NOTE_SUBTYPE and not post_data.get('partner_ids')
        if request.env.uid and (refusal := chatter_refusal(request.env, thread_model, is_note)):
            raise request.env['om.access.profile']._om_refusal(
                refusal, model=thread_model, method='message_post', record_ids=[thread_id])
        return super().mail_message_post(thread_model, thread_id, post_data, **kwargs)
