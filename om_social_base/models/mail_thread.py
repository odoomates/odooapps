from markupsafe import Markup

from odoo import api, models
from odoo.tools import plaintext2html


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_om_social(self, account, body, address, partner=False, failure_type=False, failure_reason=False,
                           status='ready', **post_values):
        """ Post on this document a message to ``address`` (an address, or the
        user ID of a customer whose address is unknown), queued for the
        provider of ``account`` (or with ``status``), or failed right away when
        ``failure_type`` says why it cannot go. ``body`` is plain text, or
        Markup when it is html already. ``post_values`` go to
        ``message_post`` (attachment_ids, attachments, om_social_message_id...). """
        self.ensure_one()
        if body and not isinstance(body, Markup):
            body = plaintext2html(body)
        message = self.message_post(
            body=body or '',
            message_type='om_social',
            subtype_xmlid='mail.mt_note',
            om_social_account_id=account.id,
            **post_values,
        )
        if failure_type:
            status = self._om_social_failure_status(failure_type)
        message._om_social_add_notification(address, partner, status, failure_type, failure_reason)
        return message

    @api.model
    def _om_social_failure_status(self, failure_type):
        """ The status of a message that cannot go: failed; channel modules
        cancel some (an address opted out...). """
        return 'exception'

    def _get_message_create_valid_field_names(self):
        return super()._get_message_create_valid_field_names() | {'om_social_account_id', 'om_social_message_id'}

    def _notify_get_recipients(self, message, **kwargs):
        """ A message of the Social Inbox is not mailed: the customer has it in
        the channel, the users who follow the document get it in their Inbox. """
        recipients = super()._notify_get_recipients(message, **kwargs)
        if message.message_type != 'om_social':
            return recipients
        return [dict(recipient, notif='inbox') for recipient in recipients if recipient['uid'] and not recipient['share']]

    @api.model
    def notify_cancel_by_type(self, notification_type):
        super().notify_cancel_by_type(notification_type)
        if notification_type == 'om_social':
            self._notify_cancel_by_type_generic('om_social')
        return True
