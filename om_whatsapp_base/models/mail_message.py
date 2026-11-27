from odoo import api, fields, models


class MailMessage(models.Model):
    """ A WhatsApp message may be made from a WhatsApp template. """
    _inherit = 'mail.message'

    om_whatsapp_template_id = fields.Many2one(
        'om.whatsapp.template', string='WhatsApp Template', index='btree_not_null', ondelete='set null', readonly=True,
        help="The template the message was made from: a provider whose templates are approved upstream sends that.")

    @api.model
    def _om_social_guarded_fields(self):
        return super()._om_social_guarded_fields() | {'om_whatsapp_template_id'}
