from odoo import fields, models

from odoo.addons.mail.tools.discuss import Store


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def write(self, vals):
        """ A message of the contact opens 24 hours of free text again: the
        open conversations show the new end at once. """
        result = super().write(vals)
        if 'om_social_last_incoming' in vals:
            for channel in self.filtered(lambda c: c.channel_type == 'om_social'
                                         and c.om_social_account_id.provider == 'meta'):
                Store(bus_channel=channel).add(channel, '_store_om_whatsapp_window_fields')
        return result

    def _store_om_whatsapp_window_fields(self, res: Store.FieldList):
        res.attr('om_social_free_text_until', lambda channel: fields.Datetime.to_string(
            channel.om_social_account_id._om_social_free_text_until(channel)))
