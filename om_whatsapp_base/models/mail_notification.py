from odoo import _, fields, models
from odoo.exceptions import UserError

# A late or repeated status update never moves a message back.
STATUS_RANK = {'ready': 0, 'process': 0, 'pending': 1, 'sent': 2}


class MailNotification(models.Model):
    """ The status of a WhatsApp message for one recipient, with the status
    values of Odoo: ready is queued, pending is sent, sent is delivered,
    is_read is read by the customer. """
    _inherit = 'mail.notification'

    notification_type = fields.Selection(
        selection_add=[('om_whatsapp', 'WhatsApp')], ondelete={'om_whatsapp': 'cascade'})
    om_whatsapp_number = fields.Char('WhatsApp Number', groups='base.group_user')
    failure_type = fields.Selection(selection_add=[
        ('om_whatsapp_number', 'No Valid Number'),
        ('om_whatsapp_optout', 'Number Opted Out'),
        ('om_whatsapp_error', 'WhatsApp Error'),
    ])

    def _store_notification_fields(self, res):
        super()._store_notification_fields(res)
        is_whatsapp = lambda n: n.notification_type == 'om_whatsapp'  # noqa: E731
        res.attr('failure_reason', predicate=is_whatsapp)
        res.attr('om_whatsapp_read', lambda n: n.is_read and n._om_whatsapp_tracks_read(), predicate=is_whatsapp)

    def _om_whatsapp_get_status(self):
        self.ensure_one()
        status = self.notification_status
        if status == 'exception':
            return 'failed'
        if status == 'canceled':
            return 'cancel'
        if status in ('ready', 'process'):
            return 'queued'
        if self.is_read and self._om_whatsapp_tracks_read():
            return 'read'
        return 'delivered' if status == 'sent' else 'sent'

    def _om_whatsapp_set_status(self, status, failure_reason=False):
        """ Status update from the provider: sent, delivered, read, failed or
        cancel. Read is only tracked when the recipient is not a user of this
        Odoo, whose notifications are read in their Inbox. """
        notifications = self.filtered(lambda n: n.notification_type == 'om_whatsapp').sudo()
        if status in ('failed', 'cancel'):
            to_update = notifications.filtered(
                lambda n: n.notification_status not in ('exception', 'canceled') and not (n.is_read and n._om_whatsapp_tracks_read()))
            to_update.write({
                'notification_status': 'exception' if status == 'failed' else 'canceled',
                'failure_type': 'om_whatsapp_error' if status == 'failed' else False,
                'failure_reason': failure_reason,
            })
        elif status == 'read':
            to_update = notifications.filtered(
                lambda n: n.notification_status in STATUS_RANK and n._om_whatsapp_tracks_read() and not n.is_read)
            to_update.write({'notification_status': 'sent', 'is_read': True, 'failure_type': False, 'failure_reason': False})
        else:
            target = {'sent': 'pending', 'delivered': 'sent'}[status]
            to_update = notifications.filtered(
                lambda n: STATUS_RANK.get(n.notification_status, 99) < STATUS_RANK[target])
            just_sent = to_update.filtered(lambda n: n.notification_status in ('ready', 'process'))
            to_update.write({'notification_status': target, 'failure_type': False, 'failure_reason': False})
            just_sent._om_whatsapp_copy_to_conversation()
        to_update.mail_message_id._notify_message_notification_update()
        return to_update

    def _om_whatsapp_copy_to_conversation(self):
        """ A message sent from a document goes to the WhatsApp conversation
        with its number too, once it is sent. """
        for notification in self.filtered(lambda n: n.om_whatsapp_number):
            message = notification.mail_message_id
            account = message.om_whatsapp_account_id
            if not account or message.model == 'discuss.channel':
                continue
            channel = account._om_whatsapp_get_channel(notification.om_whatsapp_number, notification.res_partner_id)
            document = self.env[message.model].browse(message.res_id) if message.model in self.env else None
            channel._om_whatsapp_set_document(document)
            attachments = message.attachment_ids.sudo()
            channel._message_om_whatsapp(
                account, message.body, notification.om_whatsapp_number, partner=notification.res_partner_id,
                status=notification.notification_status,
                author_id=message.author_id.id,
                om_whatsapp_id=message.om_whatsapp_id or False,
                attachment_ids=[attachment.copy({'res_model': 'discuss.channel', 'res_id': channel.id}).id
                                for attachment in attachments],
            )

    def _om_whatsapp_tracks_read(self):
        self.ensure_one()
        return not self.res_partner_id or self.res_partner_id.partner_share

    def _om_whatsapp_send(self):
        """ Hand the queued notifications to the provider of their account.
        Return the action of the provider, when there is one account. """
        to_send = self.filtered(lambda n: n.notification_type == 'om_whatsapp' and n.notification_status == 'ready')
        if not to_send:
            raise UserError(_("There is no queued WhatsApp message to send."))
        accounts = to_send.mail_message_id.om_whatsapp_account_id
        if len(to_send.mail_message_id) != len(to_send.mail_message_id.filtered('om_whatsapp_account_id')):
            raise UserError(_("A WhatsApp message has no account to send from."))
        action = None
        for account in accounts:
            action = account._om_whatsapp_send(to_send.filtered(lambda n: n.mail_message_id.om_whatsapp_account_id == account))
        return action if len(accounts) == 1 else None
