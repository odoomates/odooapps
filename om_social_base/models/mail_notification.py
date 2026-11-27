from odoo import _, fields, models
from odoo.exceptions import UserError

# A late or repeated status update never moves a message back.
STATUS_RANK = {'ready': 0, 'process': 0, 'pending': 1, 'sent': 2}


class MailNotification(models.Model):
    """ The status of a message of the Social Inbox for one recipient, with
    the status values of Odoo: ready is queued, pending is sent, sent is
    delivered, is_read is read by the customer. """
    _inherit = 'mail.notification'

    notification_type = fields.Selection(
        selection_add=[('om_social', 'Social Message')], ondelete={'om_social': 'cascade'})
    om_social_address = fields.Char(
        'Customer Address', groups='base.group_user',
        help="Where the message goes: the phone number or the handle of the customer, else the user ID the channel "
             "gives them.")
    failure_type = fields.Selection(selection_add=[('om_social_error', 'Sending Error')])

    def _store_notification_fields(self, res):
        super()._store_notification_fields(res)
        is_social = lambda n: n.notification_type == 'om_social'  # noqa: E731
        res.attr('failure_reason', predicate=is_social)
        res.attr('om_social_read', lambda n: n.is_read and n._om_social_tracks_read(), predicate=is_social)
        res.attr('om_social_channel', lambda n: n.sudo().mail_message_id.om_social_account_id.channel or False,
                 predicate=is_social)

    def _om_social_get_status(self):
        self.ensure_one()
        status = self.notification_status
        if status == 'exception':
            return 'failed'
        if status == 'canceled':
            return 'cancel'
        if status in ('ready', 'process'):
            return 'queued'
        if self.is_read and self._om_social_tracks_read():
            return 'read'
        return 'delivered' if status == 'sent' else 'sent'

    def _om_social_set_status(self, status, failure_reason=False):
        """ Status update from the provider: sent, delivered, read, failed or
        cancel. Read is only tracked when the recipient is not a user of this
        Odoo, whose notifications are read in their Inbox. """
        notifications = self.filtered(lambda n: n.notification_type == 'om_social').sudo()
        if status in ('failed', 'cancel'):
            to_update = notifications.filtered(
                lambda n: n.notification_status not in ('exception', 'canceled') and not (n.is_read and n._om_social_tracks_read()))
            to_update.write({
                'notification_status': 'exception' if status == 'failed' else 'canceled',
                'failure_type': 'om_social_error' if status == 'failed' else False,
                'failure_reason': failure_reason,
            })
        elif status == 'read':
            to_update = notifications.filtered(
                lambda n: n.notification_status in STATUS_RANK and n._om_social_tracks_read() and not n.is_read)
            to_update.write({'notification_status': 'sent', 'is_read': True, 'failure_type': False, 'failure_reason': False})
        else:
            target = {'sent': 'pending', 'delivered': 'sent'}[status]
            to_update = notifications.filtered(
                lambda n: STATUS_RANK.get(n.notification_status, 99) < STATUS_RANK[target])
            just_sent = to_update.filtered(lambda n: n.notification_status in ('ready', 'process'))
            to_update.write({'notification_status': target, 'failure_type': False, 'failure_reason': False})
            just_sent._om_social_copy_to_conversation()
        to_update.mail_message_id._notify_message_notification_update()
        return to_update

    def _om_social_copy_to_conversation(self):
        """ A message sent from a document goes to the conversation with its
        customer too, once it is sent. """
        for notification in self.filtered('om_social_address'):
            message = notification.mail_message_id
            account = message.om_social_account_id
            if not account or message.model == 'discuss.channel':
                continue
            address = notification.om_social_address
            user_ref = address if account._om_social_is_user_ref(address) else False
            channel = account._om_social_get_channel(False if user_ref else address, notification.res_partner_id,
                                                     user_ref=user_ref)
            document = self.env[message.model].browse(message.res_id) if message.model in self.env else None
            channel._om_social_set_document(document)
            attachments = message.attachment_ids.sudo()
            channel._message_om_social(
                account, message.body, address, partner=notification.res_partner_id,
                status=notification.notification_status,
                author_id=message.author_id.id,
                om_social_message_id=message.om_social_message_id or False,
                attachment_ids=[attachment.copy({'res_model': 'discuss.channel', 'res_id': channel.id}).id
                                for attachment in attachments],
            )

    def _om_social_tracks_read(self):
        self.ensure_one()
        return not self.res_partner_id or self.res_partner_id.partner_share

    def _om_social_send(self):
        """ Hand the queued notifications to the provider of their account.
        Return the action of the provider, when there is one account. """
        to_send = self.filtered(lambda n: n.notification_type == 'om_social' and n.notification_status == 'ready')
        if not to_send:
            raise UserError(_("There is no queued message to send."))
        accounts = to_send.mail_message_id.om_social_account_id
        if len(to_send.mail_message_id) != len(to_send.mail_message_id.filtered('om_social_account_id')):
            raise UserError(_("A message has no account to send from."))
        action = None
        for account in accounts:
            action = account._om_social_send(to_send.filtered(lambda n: n.mail_message_id.om_social_account_id == account))
        return action if len(accounts) == 1 else None
