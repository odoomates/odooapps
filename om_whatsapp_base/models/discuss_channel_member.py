from odoo import models


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    # the receipts of a reading go for the last messages only: older ones were read on the phone
    _OM_WHATSAPP_RECEIPT_LIMIT = 50

    def _mark_as_read(self, last_message_id, **kwargs):
        """ A user of the account who reads a WhatsApp conversation: WhatsApp
        shows the messages of the contact read (blue ticks). """
        super()._mark_as_read(last_message_id, **kwargs)
        channel = self.channel_id
        if (channel.channel_type != 'om_whatsapp' or self.partner_id != self.env.user.partner_id
                or self.env.user not in channel.om_whatsapp_account_id.user_ids):
            return
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('id', '<=', last_message_id),
            ('message_type', '=', 'om_whatsapp'), ('om_whatsapp_id', '!=', False), ('om_whatsapp_receipt', '=', False),
        ], order='id desc', limit=self._OM_WHATSAPP_RECEIPT_LIMIT)
        messages.with_env(self.env)._om_whatsapp_send_receipts('read')
