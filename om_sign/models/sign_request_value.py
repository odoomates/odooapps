import base64

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date
from odoo.tools.mimetypes import guess_mimetype

from .sign_template import FIELD_TYPES, IMAGE_TYPES


class SignRequestValue(models.Model):
    """ A field of a template-based request, for one signer, and what they filled in.

    Made when the request is sent, from the fields of its template: the request keeps its own copy of their place,
    so a template changed later changes nothing of the documents already sent. Filled by the signer only, from the
    signing page; nobody changes it by hand. """
    _name = 'sign.request.value'
    _description = 'Signature Request Field'
    _order = 'page, pos_y, pos_x, id'

    request_id = fields.Many2one('sign.request', required=True, ondelete='cascade', index=True, readonly=True)
    signer_id = fields.Many2one('sign.request.signer', required=True, ondelete='cascade', index=True, readonly=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True, index=True)
    field_id = fields.Many2one('sign.template.field', string='Template Field', ondelete='set null', readonly=True)
    role_name = fields.Char(related='signer_id.role_name', string='Role')
    type = fields.Selection(FIELD_TYPES, required=True, readonly=True)
    label = fields.Char(readonly=True)
    required = fields.Boolean(readonly=True)
    page = fields.Integer(required=True, readonly=True)
    pos_x = fields.Float(string='Left', digits=(16, 6), required=True, readonly=True)
    pos_y = fields.Float(string='Top', digits=(16, 6), required=True, readonly=True)
    width = fields.Float(digits=(16, 6), required=True, readonly=True)
    height = fields.Float(digits=(16, 6), required=True, readonly=True)
    value_text = fields.Text(string='Text Value', readonly=True)
    value_image = fields.Image(string='Image Value', max_width=1024, max_height=512, readonly=True)
    value_bool = fields.Boolean(string='Ticked', readonly=True)
    is_filled = fields.Boolean(compute='_compute_display_value')
    display_value = fields.Char(compute='_compute_display_value', string='Value')

    @api.depends('type', 'value_text', 'value_bool', 'value_image')
    def _compute_display_value(self):
        for value in self:
            value.is_filled = value._is_filled()
            if value.type in IMAGE_TYPES:
                value.display_value = self.env._('Drawn') if value.value_image else False
            elif value.type == 'checkbox':
                value.display_value = self.env._('Ticked') if value.value_bool else self.env._('Not ticked')
            elif value.type == 'date' and value.value_text:
                value.display_value = format_date(self.env, value.value_text)
            else:
                value.display_value = value.value_text

    def _is_filled(self):
        self.ensure_one()
        if self.type in IMAGE_TYPES:
            return bool(self.value_image)
        if self.type == 'checkbox':
            return self.value_bool
        return bool(self.value_text)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise UserError(self.env._('The fields of a request are made when it is sent.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._('A field is filled by its signer, not changed by hand.'))
        return super().write(vals)

    def _describe(self):
        """ :return: how the field is named to the signer, e.g. "Job title (page 2)" """
        self.ensure_one()
        name = self.label or dict(self._fields['type']._description_selection(self.env)).get(self.type)
        return self.env._('%(name)s (page %(page)s)', name=name, page=self.page)

    def _signing_values(self):
        """ :return: what the signing page shows of the field """
        self.ensure_one()
        return {
            'id': self.id,
            'type': self.type,
            'label': self.label or '',
            'required': self.required,
            'page': self.page,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'width': self.width,
            'height': self.height,
            'value': self.value_bool if self.type == 'checkbox'
                else bool(self.value_image) if self.type in IMAGE_TYPES else (self.value_text or ''),
        }

    def _signed_values(self):
        """ :return: what the signing page shows of the field filled by another signer: its place and its value,
                     a text as stamped, a ticked box or an image as a data URI """
        self.ensure_one()
        values = {
            'id': self.id,
            'type': self.type,
            'role': self.role_name or '',
            'page': self.page,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'width': self.width,
            'height': self.height,
        }
        if self.type in IMAGE_TYPES:
            content = self.value_image.content if self.value_image else b''
            values['image'] = 'data:%s;base64,%s' % (guess_mimetype(content), base64.b64encode(content).decode()) \
                if content else False
        elif self.type == 'checkbox':
            values['ticked'] = self.value_bool
        else:
            values['text'] = self.display_value or ''
        return values
