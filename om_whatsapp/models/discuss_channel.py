from odoo import fields, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def write(self, vals):
        """ A message of the contact opens 24 hours of free text again: the
        open conversations show the new end at once. """
        result = super().write(vals)
        if 'om_whatsapp_last_incoming' in vals:
            for channel in self.filtered(lambda c: c.channel_type == 'om_whatsapp'
                                         and c.om_whatsapp_account_id.provider == 'meta'):
                self.env['bus.bus']._sendone(channel, 'mail.record/insert', {'Thread': {
                    'id': channel.id, 'model': 'discuss.channel', **channel._om_whatsapp_window_values()}})
        return result

    def _om_whatsapp_window_values(self):
        self.ensure_one()
        return {'om_whatsapp_free_text_until': fields.Datetime.to_string(
            self.om_whatsapp_account_id._om_whatsapp_free_text_until(self))}
