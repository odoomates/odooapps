import logging

from markupsafe import Markup

from odoo import api, models
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_om_whatsapp(self, account, body, number, partner=False, failure_type=False, failure_reason=False,
                             status='ready', **post_values):
        """ Post on this document a WhatsApp message to ``number``, queued for
        the provider of ``account`` (or with ``status``), or failed or
        cancelled right away when ``failure_type`` says why it cannot go.
        ``body`` is plain text, or Markup when it is html already.
        ``post_values`` go to ``message_post`` (attachment_ids, attachments,
        om_whatsapp_id...). """
        self.ensure_one()
        if body and not isinstance(body, Markup):
            body = plaintext2html(body)
        message = self.message_post(
            body=body or '',
            message_type='om_whatsapp',
            subtype_xmlid='mail.mt_note',
            om_whatsapp_account_id=account.id,
            **post_values,
        )
        if failure_type == 'om_whatsapp_optout':
            status = 'canceled'
        elif failure_type:
            status = 'exception'
        message._om_whatsapp_add_notification(number, partner, status, failure_type, failure_reason)
        return message

    def _message_om_whatsapp_template(self, template, account=False):
        """ Send ``template`` from each of these records, as the composer
        does, without a user at the screen: for automation rules and code.
        The account is ``account``, else the one of the template, else the
        one of the user. Sending a WhatsApp never stops the business flow
        that triggers it (the confirmation of an order...): a problem is
        logged, and shown on the messages that could not go.

        :return: the messages posted
        """
        Message = self.env['mail.message']
        account = account or template.account_id or self.env['om.whatsapp.account']._get_default_account()
        if not self or not account:
            if self:
                _logger.warning("WhatsApp %s not sent from %s: no WhatsApp account", template.name, self)
            return Message
        try:
            with self.env.cr.savepoint():
                # sudo: the user who confirms an order needs no access to the composer
                composer = self.env['om.whatsapp.composer'].sudo().with_context(
                    active_model=self._name, active_ids=self.ids, active_id=self.ids[0],
                ).create({'account_id': account.id, 'template_id': template.id})
                messages = composer._post_messages(composer._get_records())
                queued = messages._om_whatsapp_notifications().filtered(lambda n: n.notification_status == 'ready')
                if queued:
                    account.sudo()._om_whatsapp_send_automated(queued)
        except Exception:
            _logger.exception("WhatsApp %s not sent from %s", template.name, self)
            return Message
        return messages.with_env(self.env)

    def _get_message_create_valid_field_names(self):
        return super()._get_message_create_valid_field_names() | {
            'om_whatsapp_account_id', 'om_whatsapp_id', 'om_whatsapp_template_id'}

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        """ A WhatsApp message is not mailed: the customer has it in WhatsApp,
        the users who follow the document get it in their Inbox. """
        recipients = super()._notify_get_recipients(message, msg_vals, **kwargs)
        if message.message_type != 'om_whatsapp':
            return recipients
        return [dict(recipient, notif='inbox') for recipient in recipients if recipient['uid'] and not recipient['share']]

    @api.model
    def notify_cancel_by_type(self, notification_type):
        super().notify_cancel_by_type(notification_type)
        if notification_type == 'om_whatsapp':
            self._notify_cancel_by_type_generic('om_whatsapp')
        return True
