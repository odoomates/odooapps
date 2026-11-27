import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_om_whatsapp(self, account, body, number, partner=False, failure_type=False, failure_reason=False,
                             status='ready', om_whatsapp_user_id=False, **post_values):
        """ Post on this document a WhatsApp message to ``number`` (or to the
        WhatsApp user ID ``om_whatsapp_user_id`` without one): see
        ``_message_om_social``. ``post_values`` go to ``message_post``; the
        id of the message in WhatsApp may be given as ``om_whatsapp_id``. """
        if 'om_whatsapp_id' in post_values:
            post_values['om_social_message_id'] = post_values.pop('om_whatsapp_id')
        if failure_type == 'om_whatsapp_error':
            failure_type = 'om_social_error'
        return self._message_om_social(account, body, number or om_whatsapp_user_id or False, partner=partner,
                                       failure_type=failure_type, failure_reason=failure_reason, status=status,
                                       **post_values)

    @api.model
    def _om_social_failure_status(self, failure_type):
        """ A number opted out is not a failure: the message is cancelled. """
        if failure_type == 'om_whatsapp_optout':
            return 'canceled'
        return super()._om_social_failure_status(failure_type)

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
        account = account or template.account_id or self.env['om.social.account']._get_default_account('whatsapp')
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
                queued = messages._om_social_notifications().filtered(lambda n: n.notification_status == 'ready')
                if queued:
                    account.sudo()._om_social_send_automated(queued)
        except Exception:
            _logger.exception("WhatsApp %s not sent from %s", template.name, self)
            return Message
        return messages.with_env(self.env)

    def _get_message_create_valid_field_names(self):
        return super()._get_message_create_valid_field_names() | {'om_whatsapp_template_id'}
