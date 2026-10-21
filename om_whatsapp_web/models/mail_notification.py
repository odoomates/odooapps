from urllib.parse import quote

from odoo import _, models
from odoo.exceptions import UserError


class MailNotification(models.Model):
    _inherit = 'mail.notification'

    def _om_whatsapp_web_check(self, statuses=('ready',)):
        """ Only the users of the account move its messages, queued (ready) or
        taken by a browser (process); they may not own the notifications,
        hence the sudo once checked. """
        self.mail_message_id.check_access('read')
        for notification in self.sudo():
            account = notification.mail_message_id.om_whatsapp_account_id
            if (notification.notification_type != 'om_whatsapp' or notification.notification_status not in statuses
                    or account.provider != 'web'):
                raise UserError(_("Only queued messages of a WhatsApp Web account can be sent from the browser."))
            account._om_whatsapp_check_user()
        return self.sudo()

    def _om_whatsapp_web_phone(self):
        return ''.join(char for char in self.om_whatsapp_number or '' if char.isdigit())

    def om_whatsapp_web_payload(self):
        """ What the browser hands to the extension; the files are fetched by
        the browser from /web/content. The browser that asks first takes the
        messages: another one, open on the same Odoo, gets none of them. """
        queued = self.sudo().filtered(lambda n: n.notification_status == 'ready').with_env(self.env)
        taken = queued._om_whatsapp_web_check()
        taken.write({'notification_status': 'process'})
        return [{
            'id': notification.id,
            'recipient': notification.res_partner_id.name or notification.om_whatsapp_number,
            'phone': notification._om_whatsapp_web_phone(),
            'body': notification.mail_message_id._om_whatsapp_text(),
            'quoted': notification.mail_message_id._om_whatsapp_quoted(),
            'attachments': [{
                'id': attachment.id,
                'name': attachment.name,
                'mimetype': attachment.mimetype,
            } for attachment in notification.mail_message_id.attachment_ids],
        } for notification in taken]

    def om_whatsapp_web_done(self, error=False, whatsapp_id=False):
        """ The extension's answer: sent, with the id WhatsApp gave the
        message when it knows it, or the reason it could not send. The reader
        may have seen the message sent already: the answer then changes
        nothing. """
        notifications = self._om_whatsapp_web_check(statuses=('process', 'pending', 'sent'))
        if error:
            notifications.filtered(lambda n: n.notification_status == 'process')._om_whatsapp_set_status('failed', error)
            return
        if whatsapp_id and len(notifications) == 1 and not notifications.mail_message_id.om_whatsapp_id:
            notifications.mail_message_id.om_whatsapp_id = whatsapp_id
        notifications._om_whatsapp_set_status('sent')

    def om_whatsapp_web_cancel(self):
        self._om_whatsapp_web_check(statuses=('ready', 'process'))._om_whatsapp_set_status('cancel')

    def om_whatsapp_web_fallback(self):
        """ No extension in this browser: open the chat in WhatsApp Web with
        the text filled in, for the user to send. Files cannot go that way,
        and Odoo cannot know whether it was sent. """
        self.ensure_one()
        notification = self._om_whatsapp_web_check()
        notification._om_whatsapp_set_status('sent')
        text = notification.mail_message_id._om_whatsapp_text()
        return {
            'type': 'ir.actions.act_url',
            'url': f'https://web.whatsapp.com/send?phone={notification._om_whatsapp_web_phone()}&text={quote(text)}',
            'target': 'new',
            'close': True,
        }
