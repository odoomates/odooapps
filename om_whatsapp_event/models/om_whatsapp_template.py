from odoo import api, models
from odoo.fields import Domain


class OmWhatsappTemplate(models.Model):
    _inherit = 'om.whatsapp.template'

    @api.model
    def _search(self, domain, *args, **kwargs):
        """ The template field of the event communication offers the
        templates of the registrations only: its context asks for them, as a
        reference field takes no domain. """
        if self.env.context.get('filter_template_on_event'):
            domain = Domain('model', '=', 'event.registration') & Domain(domain)
        return super()._search(domain, *args, **kwargs)

    def unlink(self):
        references = [f"{template._name},{template.id}" for template in self]
        res = super().unlink()
        self.env['event.mail'].sudo().search([('template_ref', 'in', references)]).unlink()
        self.env['event.type.mail'].sudo().search([('template_ref', 'in', references)]).unlink()
        return res
