from odoo import models


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    def om_whatsapp_event_place(self):
        """ Where the event takes place, as a sentence: its address, or its
        page for an online event. """
        self.ensure_one()
        self.check_access('read')
        event = self.event_id
        if event.contact_address_inline:
            return self.env._("Address: %(address)s.", address=event.contact_address_inline)
        if 'website_url' in event._fields and event.website_url:
            return self.env._("Details: %(url)s", url=event.get_base_url() + event.website_url)
        return ''
