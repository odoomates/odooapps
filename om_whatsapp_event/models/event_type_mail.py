from odoo import fields, models


class EventTypeMail(models.Model):
    _inherit = 'event.type.mail'

    notification_type = fields.Selection(selection_add=[('om_whatsapp', 'WhatsApp')])
    template_ref = fields.Reference(ondelete={'om.whatsapp.template': 'cascade'},
                                    selection_add=[('om.whatsapp.template', 'WhatsApp')])

    def _compute_notification_type(self):
        super()._compute_notification_type()
        self.filtered(
            lambda s: s.template_ref and s.template_ref._name == 'om.whatsapp.template').notification_type = 'om_whatsapp'
