import base64
import binascii
import io
import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.binary import BinaryBytes
from odoo.tools.mimetypes import guess_mimetype
from odoo.tools.pdf import PdfFileReader, PdfReadError

_logger = logging.getLogger(__name__)

FIELD_TYPES = [
    ('signature', 'Signature'),
    ('initials', 'Initials'),
    ('name', 'Name'),
    ('email', 'Email'),
    ('company', 'Company'),
    ('date', 'Date'),
    ('text', 'Text'),
    ('checkbox', 'Checkbox'),
]
# the fields holding a drawn image, and those the signing page fills by itself
IMAGE_TYPES = ('signature', 'initials')
AUTO_TYPES = ('email', 'company', 'date')
SIGNER_TYPES = [
    ('choose', 'Chosen When Sending'),
    ('partner', 'Given Contact'),
    ('requester', 'Person Sending'),
]
# a field may come out of its page by a rounding error, not more
TOLERANCE = 1e-6
# the picture of the first page, drawn by the browser: its types and its size at most, in bytes
THUMBNAIL_TYPES = ('image/png', 'image/jpeg', 'image/webp')
THUMBNAIL_LIMIT = 1024 * 1024


def pdf_page_count(data):
    """ :return: the number of pages of the PDF `data` (bytes), 0 when it cannot be read """
    if not data or not data.startswith(b'%PDF'):
        return 0
    try:
        return len(PdfFileReader(io.BytesIO(data), strict=False).pages)
    except (PdfReadError, ValueError, TypeError, KeyError) as error:
        _logger.info('Unreadable PDF: %s', error)
        return 0


class SignTemplate(models.Model):
    """ A PDF prepared for signature: the roles signing it and the fields each of them fills, placed on its pages.
    Sent as many times as needed, each time a request with its own copy of the PDF. """
    _name = 'sign.template'
    _inherit = ['mail.thread']
    _description = 'Sign Template'
    _check_company_auto = True
    _order = 'name, id'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    document_file = fields.Binary(string='PDF', attachment=True, required=True, copy=True)
    document_filename = fields.Char()
    page_count = fields.Integer(string='Pages', compute='_compute_page_count', store=True)
    document_checksum = fields.Char(compute='_compute_document_checksum',
                                    help='The checksum of the PDF, to tell whether its thumbnail is of it.')
    thumbnail = fields.Image(max_width=480, max_height=480, attachment=True, copy=True, readonly=True,
                             help='The first page of the PDF, drawn by the browser the first time it is shown.')
    role_ids = fields.One2many('sign.template.role', 'template_id', string='Roles', copy=True)
    field_ids = fields.One2many('sign.template.field', 'template_id', string='Fields')
    field_count = fields.Integer(compute='_compute_field_count', string='Number of Fields')
    request_ids = fields.One2many('sign.request', 'sign_template_id', string='Requests')
    request_count = fields.Integer(compute='_compute_request_count', string='Requests Count')
    sent_request_count = fields.Integer(compute='_compute_request_count', string='Sent')
    signed_request_count = fields.Integer(compute='_compute_request_count', string='Signed')
    email_code = fields.Boolean(help='Each signer gets a code by email and enters it before signing.')
    validity_days = fields.Integer(string='Days to Sign', default=14,
                                   help='The request expires after these days. 0 for no deadline.')
    reminder_days = fields.Integer(string='Remind Every', default=3,
                                   help='Days between the reminders to a signer. 0 for no reminder.')
    message = fields.Text(help='Proposed to the person sending, shown to the signers in the email and on the signing '
                               'page.')
    company_id = fields.Many2one('res.company', index=True, default=lambda self: self.env.company,
                                 help='Leave empty to share the template with all the companies.')
    cc_partner_ids = fields.Many2many(
        'res.partner', 'sign_template_cc_partner_rel', 'template_id', 'partner_id', string='Copy To',
        help='Proposed when sending: these contacts do not sign, they are told and get the signed PDF.')
    cc_notify_sent = fields.Boolean(string='Tell Them When Sent', default=True,
                                    help='The copy recipients get an email when the document is sent for signature, '
                                         'not only once it is signed.')
    share_enabled = fields.Boolean(
        string='Share Link', copy=False, tracking=True,
        help='Anyone with the link signs the template as its role chosen when sending, once they confirmed their '
             'email with a code.')
    share_token = fields.Char(copy=False, readonly=True, groups='om_sign.group_sign_user')
    share_user_id = fields.Many2one('res.users', string='Shared By', copy=False, readonly=True,
                                    help='Signs as the person sending, and follows the requests made from the link.')
    share_url = fields.Char(string='Link', compute='_compute_share_url')
    share_role_id = fields.Many2one('sign.template.role', string='Visitor Signs As', compute='_compute_share_role')
    share_problem = fields.Char(compute='_compute_share_role')
    share_request_count = fields.Integer(compute='_compute_request_count', string='Requests From the Link')

    @api.depends('document_file')
    def _compute_page_count(self):
        for template in self:
            data = template.document_file
            template.page_count = pdf_page_count(data.content if data else b'')

    @api.depends('field_ids')
    def _compute_field_count(self):
        for template in self:
            template.field_count = len(template.field_ids)

    @api.depends('document_file')
    def _compute_document_checksum(self):
        checksums = {
            attachment['res_id']: attachment['checksum']
            for attachment in self.env['ir.attachment'].sudo().search_read([
                ('res_model', '=', self._name), ('res_field', '=', 'document_file'), ('res_id', 'in', self.ids),
            ], ['res_id', 'checksum'])
        } if self.ids else {}
        for template in self:
            template.document_checksum = checksums.get(template.id, False)

    def _compute_request_count(self):
        groups = self.env['sign.request']._read_group(
            [('sign_template_id', 'in', self.ids)], ['sign_template_id', 'source', 'state'], ['__count'])
        for template in self:
            mine = [(source, state, count) for group, source, state, count in groups if group == template]
            template.request_count = sum(count for _source, _state, count in mine)
            template.sent_request_count = sum(count for _source, state, count in mine if state != 'draft')
            template.signed_request_count = sum(count for _source, state, count in mine if state == 'signed')
            template.share_request_count = sum(count for source, _state, count in mine if source == 'share_link')

    @api.depends('share_enabled')
    def _compute_share_url(self):
        for template in self:
            token = template.sudo().share_token
            template.share_url = '%s/sign/share/%s/%s' % (template.get_base_url(), template.id, token) \
                if template.share_enabled and token and template.id else False

    @api.depends('role_ids.signer_type', 'role_ids.partner_id')
    def _compute_share_role(self):
        for template in self:
            chosen = template.role_ids.filtered(lambda role: role.signer_type == 'choose')
            template.share_role_id = chosen if len(chosen) == 1 else False
            template.share_problem = False if len(chosen) == 1 else self.env._(
                'To be shared by a link, exactly one role is "Chosen When Sending": the visitor signs as it. The '
                'other roles are a given contact or the person sending.')

    @api.constrains('document_file')
    def _check_document(self):
        for template in self:
            if not template.page_count:
                raise ValidationError(self.env._('%s is not a PDF file that can be read.',
                                                 template.document_filename or template.name))
            if template.field_ids and max(template.field_ids.mapped('page')) > template.page_count:
                raise ValidationError(self.env._('The new PDF of %s has fewer pages than its fields need.',
                                                 template.name))

    @api.constrains('share_enabled', 'role_ids')
    def _check_share(self):
        for template in self:
            if template.share_enabled and template.share_problem:
                raise ValidationError(template.share_problem)

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates.filtered('share_enabled')._sync_share()
        return templates

    def write(self, vals):
        if 'document_file' in vals and 'thumbnail' not in vals:
            # the picture of the old PDF: the next time it is shown, the browser draws the new one
            vals = {**vals, 'thumbnail': False}
        result = super().write(vals)
        if 'share_enabled' in vals:
            self._sync_share()
        return result

    def _sync_share(self):
        """ A template shared gets its link, shared by the user sharing it; no longer shared, the link stops. """
        for template in self.sudo():
            if template.share_enabled and not template.share_token:
                template.write({'share_token': secrets.token_urlsafe(24), 'share_user_id': self.env.uid})
            elif not template.share_enabled and template.share_token:
                template.share_token = False

    @api.ondelete(at_uninstall=False)
    def _unlink_except_sent(self):
        for template in self:
            if template.sudo().request_ids:
                raise UserError(self.env._('Documents were sent from %s: archive it instead.', template.name))

    def copy(self, default=None):
        """ The fields of the copy belong to the copied roles. """
        templates = super().copy(default=default)
        for original, template in zip(self, templates, strict=True):
            roles = dict(zip(original.role_ids, template.role_ids, strict=True))
            for field in original.field_ids:
                field.copy({'template_id': template.id, 'role_id': roles[field.role_id].id})
        return templates

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_open_editor(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'om_sign_template_editor',
            'name': self.name,
            'params': {'template_id': self.id},
            'context': {'active_id': self.id},
        }

    def action_send(self):
        """ The wizard choosing who signs. """
        self.ensure_one()
        if not self.role_ids:
            raise UserError(self.env._('Add the roles signing %s first.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Send %s', self.name),
            'res_model': 'sign.send',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_template_id': self.id},
        }

    def action_send_bulk(self):
        """ The wizard sending one request per contact, for one role. """
        self.ensure_one()
        if not self.role_ids:
            raise UserError(self.env._('Add the roles signing %s first.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Send %s in Bulk', self.name),
            'res_model': 'sign.send',
            'view_mode': 'form',
            'views': [(self.env.ref('om_sign.sign_send_view_form_bulk').id, 'form')],
            'target': 'new',
            'context': {'default_template_id': self.id, 'default_bulk': True},
        }

    def action_open_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Requests'),
            'res_model': 'sign.request',
            'view_mode': 'kanban,list,form',
            'views': [(self.env.ref('om_sign.sign_request_view_kanban_flat').id, 'kanban'), (False, 'list'),
                      (False, 'form')],
            'domain': [('sign_template_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_open_share_requests(self):
        action = self.action_open_requests()
        action.update(name=self.env._('Requests From the Link'),
                      domain=[('sign_template_id', '=', self.id), ('source', '=', 'share_link')])
        return action

    def action_open_sent_requests(self):
        action = self.action_open_requests()
        action.update(name=self.env._('Sent'), domain=[('sign_template_id', '=', self.id), ('state', '!=', 'draft')])
        return action

    def action_open_signed_requests(self):
        action = self.action_open_requests()
        action.update(name=self.env._('Signed'), domain=[('sign_template_id', '=', self.id), ('state', '=', 'signed')])
        return action

    def save_thumbnail(self, data, checksum):
        """ Keep the picture of the first page of the PDF, drawn by the browser of a user who shows the template
        (the server cannot draw a PDF by itself). Kept only from a user who may change the template, and only when it
        is of the PDF the template still has.

        :param data: the picture, PNG, JPEG or WebP, in base64 or as a data URI
        :param checksum: the `document_checksum` of the PDF the picture was drawn from
        :return: whether it was kept """
        self.ensure_one()
        if not self.has_access('write') or not checksum or checksum != self.document_checksum:
            return False
        if not isinstance(data, str) or len(data) > THUMBNAIL_LIMIT * 4 // 3 + 64:
            return False
        try:
            image = base64.b64decode(data.split(',', 1)[-1] if data.startswith('data:') else data, validate=True)
        except (binascii.Error, ValueError):
            return False
        if guess_mimetype(image) not in THUMBNAIL_TYPES:
            return False
        # readonly for the users: only kept from here
        self.sudo().thumbnail = BinaryBytes(image)
        return True

    def action_regenerate_share_token(self):
        """ A new link: the one given so far no longer opens. """
        for template in self:
            if not template.share_enabled:
                raise UserError(self.env._('Share %s by a link first.', template.name))
            template.sudo().share_token = secrets.token_urlsafe(24)
        return True

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    def _share_user(self):
        """ :return: the user the requests of the shared link are sent as """
        self.ensure_one()
        return self.sudo().share_user_id or self.sudo().create_uid

    def _prepare_request(self, partners, **values):
        """ :param partners: {sign.template.role: res.partner signing as it}, for each role of the template
            :param values: other values of the request, e.g. its message
            :return: the values of a request of the template, its signers in the order of the roles """
        self.ensure_one()
        return {
            'name': self.name,
            'sign_template_id': self.id,
            'document_file': BinaryBytes(self.sudo().document_file.content),
            'document_filename': self.document_filename,
            'company_id': (self.company_id or self.env.company).id,
            'signer_ids': [Command.create({
                'sequence': role.sequence,
                'role_name': role.name,
                'template_role_id': role.id,
                'partner_id': partners[role].id,
            }) for role in self.role_ids],
            **values,
        }

    def _request_defaults(self):
        """ :return: what a request of the template gets by default: its message, deadline, reminders... """
        return {
            'message': self.message,
            'date_deadline': fields.Date.context_today(self) + timedelta(days=self.validity_days)
                if self.validity_days else False,
            'reminder_days': self.reminder_days,
            'email_code': self.email_code,
            'cc_partner_ids': [Command.set(self.cc_partner_ids.ids)],
            'cc_notify_sent': self.cc_notify_sent,
        }

    # ------------------------------------------------------------------
    # The editor
    # ------------------------------------------------------------------

    @api.model
    def _editor_selections(self):
        Field, Role = self.env['sign.template.field'], self.env['sign.template.role']
        return {
            'types': Field._fields['type']._description_selection(self.env),
            'signer_types': Role._fields['signer_type']._description_selection(self.env),
        }

    def _editor_data(self):
        """ :return: what the editor shows of the template """
        self.ensure_one()
        return {
            'template': {
                'id': self.id,
                'name': self.name,
                'filename': self.document_filename or '',
                'page_count': self.page_count,
                'pdf_url': '/web/content/sign.template/%s/document_file' % self.id,
                'request_count': self.request_count,
                'active': self.active,
            },
            'share': self._editor_share(),
            'roles': [role._editor_values() for role in self.role_ids],
            'fields': [field._editor_values() for field in self.field_ids],
            'can_edit': self.has_access('write'),
            **self._editor_selections(),
        }

    @api.model
    def editor_load(self, template_id):
        template = self.browse(template_id).exists()
        if not template:
            raise UserError(self.env._('The template no longer exists.'))
        template.check_access('read')
        return template._editor_data()

    @api.model
    def editor_save(self, template_id, data):
        """ Write the roles and the fields as the editor shows them. The roles and fields new in the editor have a
        temporary id, a string; the fields name their role by its id, temporary or not.

        :return: what the editor shows of the template once saved """
        template = self.browse(template_id).exists()
        if not template:
            raise UserError(self.env._('The template no longer exists.'))
        template.check_access('write')
        Role, Field = self.env['sign.template.role'], self.env['sign.template.field']
        roles = {}
        kept_roles = Role
        for sequence, values in enumerate(data.get('roles') or [], start=1):
            vals = Role._editor_vals(values, sequence)
            role = template.role_ids.filtered(lambda role: role.id == values.get('id'))
            if role:
                role.write(vals)
            else:
                role = Role.create({**vals, 'template_id': template.id})
            roles[values.get('id')] = role
            kept_roles |= role
        (template.role_ids - kept_roles).unlink()
        kept_fields = Field
        for values in data.get('fields') or []:
            role = roles.get(values.get('role_id'))
            if not role:
                raise UserError(self.env._('Each field must belong to a role.'))
            vals = {**Field._editor_vals(values), 'role_id': role.id}
            field = template.field_ids.filtered(lambda field: field.id == values.get('id'))
            if field:
                field.write(vals)
            else:
                field = Field.create({**vals, 'template_id': template.id})
            kept_fields |= field
        (template.field_ids - kept_fields).unlink()
        if template.share_enabled and template.share_problem:
            raise UserError(self.env._('%(template)s is shared by a link: %(problem)s', template=template.name,
                                       problem=template.share_problem))
        return template._editor_data()

    def _editor_share(self):
        self.ensure_one()
        return {
            'enabled': self.share_enabled,
            'url': self.share_url or '',
            'problem': self.share_problem or '',
            'role': self.share_role_id.name or '',
        }

    @api.model
    def editor_share(self, template_id, enabled=None, regenerate=False):
        """ Share the template by a link, or stop; or give it a new link.

        :return: what the editor shows of the sharing """
        template = self.browse(template_id).exists()
        if not template:
            raise UserError(self.env._('The template no longer exists.'))
        if enabled is not None and bool(enabled) != template.share_enabled:
            template.share_enabled = bool(enabled)
        if regenerate:
            template.action_regenerate_share_token()
        return template._editor_share()


class SignTemplateRole(models.Model):
    """ Who signs a template, and in which order. """
    _name = 'sign.template.role'
    _description = 'Sign Template Role'
    _order = 'sequence, id'

    template_id = fields.Many2one('sign.template', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True, index=True)
    name = fields.Char(string='Role', required=True, copy=True, help='e.g. Customer, Company, Employee.')
    sequence = fields.Integer(
        default=10, help='The roles of the same sequence sign together; a higher one waits for the lower ones.')
    color = fields.Integer(default=1, help='The colour of the fields of the role in the editor.')
    signer_type = fields.Selection(SIGNER_TYPES, string='Signer', required=True, default='choose')
    partner_id = fields.Many2one('res.partner', string='Contact')
    field_ids = fields.One2many('sign.template.field', 'role_id', string='Fields')

    @api.constrains('signer_type', 'partner_id')
    def _check_signer(self):
        for role in self:
            if role.signer_type == 'partner' and not role.partner_id:
                raise ValidationError(self.env._('Choose the contact signing as %s.', role.name))

    def _get_partner(self):
        """ :return: the contact signing as this role by default (empty when chosen when sending) """
        self.ensure_one()
        if self.signer_type == 'requester':
            return self.env.user.partner_id
        if self.signer_type == 'partner':
            return self.partner_id
        return self.env['res.partner']

    def _editor_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'sequence': self.sequence,
            'color': self.color,
            'signer_type': self.signer_type,
            'partner_id': self.partner_id.id,
        }

    @api.model
    def _editor_vals(self, values, sequence):
        signer_type = values.get('signer_type') or 'choose'
        return {
            'name': (values.get('name') or '').strip() or self.env._('Signer'),
            # the order of the editor list, those signing together keep one sequence
            'sequence': int(values.get('sequence') or sequence),
            'color': int(values.get('color') or 0),
            'signer_type': signer_type,
            'partner_id': (values.get('partner_id') or False) if signer_type == 'partner' else False,
        }


class SignTemplateField(models.Model):
    """ A field of a template, filled by the signers of one role. Its place is given as fractions of its page as
    the browser shows it, from the top left corner: independent of the zoom and of the size of the page. """
    _name = 'sign.template.field'
    _description = 'Sign Template Field'
    _order = 'page, pos_y, pos_x, id'

    template_id = fields.Many2one('sign.template', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True, index=True)
    role_id = fields.Many2one('sign.template.role', required=True, ondelete='cascade', index=True,
                              domain="[('template_id', '=', template_id)]")
    type = fields.Selection(FIELD_TYPES, required=True, default='signature')
    page = fields.Integer(required=True, default=1, help='The page, from 1.')
    pos_x = fields.Float(string='Left', digits=(16, 6), required=True)
    pos_y = fields.Float(string='Top', digits=(16, 6), required=True)
    width = fields.Float(digits=(16, 6), required=True, default=0.25)
    height = fields.Float(digits=(16, 6), required=True, default=0.05)
    required = fields.Boolean(default=True, help='The signer cannot sign without filling it; a required checkbox '
                                                 'must be ticked.')
    label = fields.Char(help='Shown to the signer in the field, e.g. "Job title".')

    @api.constrains('template_id', 'role_id')
    def _check_role(self):
        for field in self:
            if field.role_id.template_id != field.template_id:
                raise ValidationError(self.env._('A field belongs to a role of its own template.'))

    @api.constrains('page', 'pos_x', 'pos_y', 'width', 'height')
    def _check_place(self):
        for field in self:
            if field.page < 1 or field.page > max(field.template_id.page_count, 1):
                raise ValidationError(self.env._('%(template)s has no page %(page)s.',
                                                 template=field.template_id.name, page=field.page))
            if field.width <= 0 or field.height <= 0 or field.pos_x < -TOLERANCE or field.pos_y < -TOLERANCE \
                    or field.pos_x + field.width > 1 + TOLERANCE or field.pos_y + field.height > 1 + TOLERANCE:
                raise ValidationError(self.env._('A field must be inside its page.'))

    def _editor_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'role_id': self.role_id.id,
            'type': self.type,
            'page': self.page,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'width': self.width,
            'height': self.height,
            'required': self.required,
            'label': self.label or '',
        }

    @api.model
    def _editor_vals(self, values):
        types = dict(FIELD_TYPES)
        if values.get('type') not in types:
            raise UserError(self.env._('Unknown field type: %s', values.get('type')))
        try:
            vals = {
                'type': values['type'],
                'page': int(values.get('page') or 1),
                'pos_x': float(values.get('pos_x') or 0),
                'pos_y': float(values.get('pos_y') or 0),
                'width': float(values.get('width') or 0),
                'height': float(values.get('height') or 0),
            }
        except (TypeError, ValueError):
            raise UserError(self.env._('A field has a wrong place.')) from None
        return {**vals, 'required': bool(values.get('required')), 'label': (values.get('label') or '').strip()}
