from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SignRole(models.Model):
    """ Who signs the prints of a template, and in which order. """
    _name = 'sign.role'
    _description = 'Signer Role'
    _order = 'sequence, id'

    template_id = fields.Many2one('print.template', required=True, ondelete='cascade', index=True)
    model = fields.Char(related='template_id.model')
    sequence = fields.Integer(
        default=10, help='The roles of the same sequence sign together; a higher one waits for the lower ones.')
    name = fields.Char(string='Role', required=True, help='e.g. Employee, Manager, Customer.')
    signer_type = fields.Selection([
        ('field', 'Contact of a Field'),
        ('partner', 'Given Contact'),
        ('issuer', 'Person Sending'),
    ], string='Signer', required=True, default='field')
    partner_id = fields.Many2one('res.partner', string='Contact')
    field_path = fields.Char(
        string='Field', help='The field of the record naming the signer, e.g. partner_id for the customer of a sale '
                             'order. Leave empty when the record is the contact itself.')
    placeholder = fields.Char(compute='_compute_placeholder',
                              help='Write it in the body of the template where the signature goes; without it, the '
                                   'signature goes below the text.')

    @api.depends('name')
    def _compute_placeholder(self):
        for role in self:
            role.placeholder = '[signature: %s]' % role.name if role.name else False

    @api.constrains('signer_type', 'partner_id', 'field_path')
    def _check_signer(self):
        for role in self:
            if role.signer_type == 'partner' and not role.partner_id:
                raise ValidationError(self.env._('Choose the contact signing as %s.', role.name))
            if role.signer_type == 'field':
                role._check_field_path()

    def _check_field_path(self):
        self.ensure_one()
        model = self.env[self.template_id.model]
        try:
            for name in filter(None, (self.field_path or '').split('.')):
                model = self.env[model._fields[name].comodel_name]
        except (KeyError, AttributeError):
            raise ValidationError(self.env._('%(path)s is not a field path of %(model)s.',
                                             path=self.field_path, model=self.template_id.model_id.name)) from None
        if model._name not in self._partners_models():
            raise ValidationError(self.env._('The signer of %s must be a contact or a user.', self.name))

    @api.model
    def _partners_models(self):
        return ('res.partner', 'res.users')

    @api.model
    def _as_partners(self, records):
        """ :return: the contacts of `records`, which are of one of the models of `_partners_models` """
        if records._name == 'res.partner':
            return records
        if records._name == 'res.users':
            return records.partner_id
        return self.env['res.partner']

    def _get_partner(self, record):
        """ :return: the contact signing as this role for `record` (empty when nobody is found) """
        self.ensure_one()
        if self.signer_type == 'issuer':
            return self.env.user.partner_id
        if self.signer_type == 'partner':
            return self.partner_id
        records = record.sudo()
        if self.field_path:
            records = records.mapped(self.field_path)
        return self._as_partners(records)[:1]
