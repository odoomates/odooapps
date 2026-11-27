from odoo import models


class DiscussChannel(models.Model):
    """ A WhatsApp conversation: the chat of a WhatsApp account with one
    number, or with a WhatsApp user ID when the number is not shared. """
    _inherit = 'discuss.channel'

    def _om_social_is_of(self, partner):
        """ The customer of a WhatsApp conversation, by their number too. """
        self.ensure_one()
        if self.om_social_account_id.channel == 'whatsapp' and self.om_social_address \
                and partner.phone_sanitized == self.om_social_address:
            return True
        return super()._om_social_is_of(partner)

    def _om_social_contact_defaults(self):
        defaults = super()._om_social_contact_defaults()
        if self.om_social_account_id.channel == 'whatsapp' and self.om_social_address \
                and not self.om_social_account_id._om_social_is_user_ref(self.om_social_address):
            defaults['default_phone'] = self.om_social_address
        return defaults
