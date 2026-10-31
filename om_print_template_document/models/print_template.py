from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PrintTemplate(models.Model):
    _inherit = 'print.template'

    document_type_id = fields.Many2one(
        'document.type', string='File as Document', domain="[('res_model', '=', model)]", check_company=True,
        help='Each print is also kept as a document of this type on the record printed, with its PDF.')
    validity_days = fields.Integer(
        string='Valid For (Days)',
        help='The document expires this many days after the date of the print. Leave 0 for no expiry.')

    @api.constrains('document_type_id', 'model_id', 'validity_days')
    def _check_document_type(self):
        for template in self:
            if template.document_type_id and template.document_type_id.res_model != template.model:
                raise ValidationError(self.env._('%(template)s prints %(model)s: its documents must be of that kind '
                                                 'too.', template=template.name, model=template.model_id.name))
            if template.validity_days < 0:
                raise ValidationError(self.env._('The validity of %s cannot be negative.', template.name))
