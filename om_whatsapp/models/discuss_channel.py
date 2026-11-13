from odoo import fields, models

from odoo.addons.mail.tools.discuss import Store


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def write(self, vals):
        """ A message of the contact opens 24 hours of free text again: the
        open conversations show the new end at once. """
        result = super().write(vals)
        if 'om_whatsapp_last_incoming' in vals:
            for channel in self.filtered(lambda c: c.channel_type == 'om_whatsapp'
                                         and c.om_whatsapp_account_id.provider == 'meta'):
                Store(bus_channel=channel).add(channel, channel._om_whatsapp_window_fields()).bus_send()
        return result

    def _om_whatsapp_window_fields(self):
        return [Store.Attr('om_whatsapp_free_text_until', lambda channel: fields.Datetime.to_string(
            channel.om_whatsapp_account_id._om_whatsapp_free_text_until(channel)))]
