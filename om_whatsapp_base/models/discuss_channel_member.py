from odoo import models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    # the receipts of a reading go for the last messages only: older ones were read on the phone
    _OM_WHATSAPP_RECEIPT_LIMIT = 50

    def _set_last_seen_message(self, last_message, allow_older=False):
        """ A user of the account who reads a WhatsApp conversation: WhatsApp
        shows the messages of the contact read (blue ticks). """
        super()._set_last_seen_message(last_message, allow_older=allow_older)
        for channel in self:
            member = channel.channel_member_ids.filtered(lambda m: m.partner_id == self.env.user.partner_id)
            if (channel.channel_type != 'om_whatsapp' or not member or not last_message
                    or self.env.user not in channel.om_whatsapp_account_id.user_ids):
                continue
            messages = self.env['mail.message'].sudo().search([
                ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('id', '<=', last_message.id),
                ('message_type', '=', 'om_whatsapp'), ('om_whatsapp_id', '!=', False), ('om_whatsapp_receipt', '=', False),
            ], order='id desc', limit=self._OM_WHATSAPP_RECEIPT_LIMIT)
            messages.with_env(self.env)._om_whatsapp_send_receipts('read')
