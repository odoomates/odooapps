import base64
import binascii
import hashlib
import re
import secrets
import uuid
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import consteq
from odoo.tools.binary import BinaryBytes
from odoo.tools.mail import single_email_re
from odoo.tools.mimetypes import guess_mimetype

from .sign_template import AUTO_TYPES, IMAGE_TYPES

CODE_MINUTES = 10  # how long an email code stays valid
CODE_ATTEMPTS = 5  # wrong codes before a new one must be asked
CODE_RESEND_SECONDS = 60  # one code a minute at most
SIGNATURE_TYPES = ('image/png', 'image/jpeg', 'image/webp')
IMAGE_LIMIT = 2 * 1024 * 1024  # bytes of a drawn signature or initials
TEXT_LIMIT = 1000  # characters of a text filled in
DATA_URI = re.compile(r'^data:image/[a-z+.-]+;base64,', re.IGNORECASE)

# what only the signing itself changes, never a user editing the request
PROTECTED_FIELDS = {'state', 'signed_name', 'signature', 'date_signed', 'decline_reason', 'date_invited',
                    'date_reminded', 'date_opened', 'access_token', 'code_hash', 'code_expiry', 'code_attempts',
                    'code_verified'}


class SignRequestSigner(models.Model):
    """ One person signing a request: their turn, their signature and how they gave it. """
    _name = 'sign.request.signer'
    _description = 'Signer'
    _order = 'sequence, id'
    _rec_name = 'partner_id'

    request_id = fields.Many2one('sign.request', required=True, ondelete='cascade', index=True)
    request_state = fields.Selection(related='request_id.state', string='Request Status')
    company_id = fields.Many2one(related='request_id.company_id', store=True, index=True)
    sequence = fields.Integer(
        default=10, help='The signers of the same sequence sign together; a higher one waits for the lower ones.')
    role_name = fields.Char(string='Role')
    partner_id = fields.Many2one('res.partner', string='Signer', index=True)
    template_role_id = fields.Many2one('sign.template.role', ondelete='set null', readonly=True)
    value_ids = fields.One2many('sign.request.value', 'signer_id', string='Fields', readonly=True)
    email = fields.Char(related='partner_id.email')
    state = fields.Selection([
        ('waiting', 'Waiting for Others'),
        ('to_sign', 'To Sign'),
        ('signed', 'Signed'),
        ('declined', 'Declined'),
    ], required=True, default='waiting', copy=False, readonly=True)
    signed_name = fields.Char(string='Signed As', readonly=True, copy=False)
    signature = fields.Image(max_width=1024, max_height=512, readonly=True, copy=False)
    date_signed = fields.Datetime(string='Signed On', readonly=True, copy=False)
    decline_reason = fields.Text(readonly=True, copy=False)
    date_invited = fields.Datetime(string='Asked On', readonly=True, copy=False)
    date_reminded = fields.Datetime(string='Reminded On', readonly=True, copy=False)
    date_opened = fields.Datetime(string='Opened On', readonly=True, copy=False)
    access_token = fields.Char(copy=False, readonly=True, groups='base.group_system')
    code_hash = fields.Char(copy=False, readonly=True, groups='base.group_system')
    code_expiry = fields.Datetime(copy=False, readonly=True, groups='base.group_system')
    code_attempts = fields.Integer(copy=False, readonly=True, groups='base.group_system')
    code_verified = fields.Boolean(string='Email Verified', readonly=True, copy=False)
    is_me = fields.Boolean(compute='_compute_is_me')

    @api.depends_context('uid')
    def _compute_is_me(self):
        for signer in self:
            signer.is_me = signer.partner_id == self.env.user.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        requests = self.env['sign.request'].browse({vals.get('request_id') for vals in vals_list} - {None})
        if not self.env.su and any(request.state != 'draft' for request in requests):
            raise UserError(self.env._('The request is sent: cancel it and send another one to change its signers.'))
        signers = super().create(vals_list)
        for signer in signers.sudo():
            signer.access_token = uuid.uuid4().hex
        return signers

    def write(self, vals):
        if not self.env.su:
            if PROTECTED_FIELDS & set(vals):
                raise UserError(self.env._('A signature is given by its signer, not changed by hand.'))
            if any(signer.request_id.state != 'draft' for signer in self):
                raise UserError(self.env._('The request is sent: cancel it and send another one to change its '
                                           'signers.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_sent(self):
        if not self.env.su and any(signer.request_id.state != 'draft' for signer in self):
            raise UserError(self.env._('The request is sent: cancel it and send another one to change its signers.'))

    def _get_sign_url(self):
        self.ensure_one()
        return '%s/sign/%s/%s' % (self.get_base_url(), self.id, self.sudo().access_token)

    def _check_token(self, token):
        self.ensure_one()
        return bool(token) and consteq(self.sudo().access_token or '', token)

    # ------------------------------------------------------------------
    # Notifying
    # ------------------------------------------------------------------

    def _notify(self, template, subject, **values):
        self.ensure_one()
        body = self.env['ir.qweb']._render(template, {
            'signer': self, 'sign_request': self.request_id, 'sign_url': self._get_sign_url(), **values})
        self.request_id.sudo().message_notify(
            partner_ids=self.partner_id.ids, subject=subject, body=body,
            email_layout_xmlid='mail.mail_notification_light')

    def _send_invitation(self, reminder=False):
        self.ensure_one()
        subject = self.env._('Reminder: please sign %s', self.request_id.name) if reminder \
            else self.env._('Please sign %s', self.request_id.name)
        self._notify('om_sign.mail_sign_invitation', subject, reminder=reminder)
        self.env['sign.log']._log(self.request_id, 'reminded' if reminder else 'invited', signer=self)

    # ------------------------------------------------------------------
    # Signing, from the signing page
    # ------------------------------------------------------------------

    def _check_can_sign(self):
        self.ensure_one()
        if self.request_id.state != 'sent':
            raise UserError(self.env._('This request is no longer waiting for signatures.'))
        if self.state != 'to_sign':
            raise UserError(self.env._('It is not your turn to sign yet.') if self.state == 'waiting'
                            else self.env._('You already answered this request.'))

    def _opened(self):
        """ The signer opened the signing page; the first time is logged. """
        self.ensure_one()
        if not self.date_opened and self.state == 'to_sign':
            self.sudo().date_opened = fields.Datetime.now()
            self.env['sign.log']._log(self.request_id, 'opened', signer=self)

    def _needs_code(self):
        self.ensure_one()
        return self.request_id.email_code and not self.code_verified

    @api.model
    def _generate_code(self):
        return '%06d' % secrets.randbelow(10 ** 6)

    def _hash_code(self, code):
        return hashlib.sha256(('%s:%s' % (self.sudo().access_token, code)).encode()).hexdigest()

    def _send_code(self):
        """ Email a new code to the signer. :return: False when one was sent less than a minute ago """
        self.ensure_one()
        self._check_can_sign()
        me = self.sudo()
        now = fields.Datetime.now()
        if me.code_expiry and me.code_expiry - timedelta(minutes=CODE_MINUTES) > \
                now - timedelta(seconds=CODE_RESEND_SECONDS):
            return False
        code = self._generate_code()
        me.write({'code_hash': self._hash_code(code), 'code_attempts': 0,
                  'code_expiry': now + timedelta(minutes=CODE_MINUTES)})
        self._notify('om_sign.mail_sign_code', self.env._('Your code to sign %s', self.request_id.name), code=code,
                     minutes=CODE_MINUTES)
        self.env['sign.log']._log(self.request_id, 'code_sent', signer=self)
        return True

    def _verify_code(self, code):
        """ :return: whether `code` is the one emailed, still valid """
        self.ensure_one()
        self._check_can_sign()
        me = self.sudo()
        if not me.code_hash or me.code_attempts >= CODE_ATTEMPTS or me.code_expiry < fields.Datetime.now():
            return False
        if not consteq(self._hash_code((code or '').strip()), me.code_hash):
            me.code_attempts += 1
            self.env['sign.log']._log(self.request_id, 'code_failed', signer=self)
            return False
        me.write({'code_verified': True, 'code_hash': False})
        self.env['sign.log']._log(self.request_id, 'code_verified', signer=self)
        return True

    def _sign(self, name, signature):
        """ The signer signs as `name` with the image `signature` (base64). On a request of a template, the
        signature fills their signature and initials fields, the name their name fields, and their email, company
        and date fields are filled for them; the other fields must be filled with `_sign_fields`. """
        self.ensure_one()
        self._check_can_sign()
        if self._needs_code():
            raise UserError(self.env._('Enter the code sent to your email first.'))
        if not (name or '').strip() or not signature:
            raise UserError(self.env._('Write your name and sign.'))
        image = self._decode_image(signature)
        if self.sudo().value_ids:
            to_fill = self._fields_to_fill()
            if to_fill:
                raise UserError(self.env._('Fill in the document before signing it: %s.',
                                           ', '.join(to_fill.mapped(lambda value: value._describe()))))
            values = {}
            for value in self.sudo().value_ids:
                if value.type in IMAGE_TYPES:
                    values[value.id] = signature
                elif value.type == 'name':
                    values[value.id] = name.strip()
            return self._sign_fields(values, name=name.strip(), signature=image)
        return self._mark_signed(name.strip(), image)

    def _mark_signed(self, name, image):
        self.sudo().write({
            'signed_name': name,
            'signature': BinaryBytes(image) if image else False,
            'state': 'signed',
            'date_signed': fields.Datetime.now(),
        })
        self.env['sign.log']._log(self.request_id, 'signed', signer=self,
                                  document_hash=self.request_id.document_hash)
        self.request_id._activate_next()

    def _decode_image(self, data):
        """ :return: the bytes of the image `data` (base64, or a data URI) drawn by the signer
            :raise UserError: when it is not a PNG, JPEG or WebP image, or is too large """
        if isinstance(data, bytes):
            data = data.decode('ascii', 'replace')
        if not isinstance(data, str):
            raise UserError(self.env._('The signature could not be read. Sign again.'))
        data = DATA_URI.sub('', data.strip())
        if len(data) > IMAGE_LIMIT * 4 // 3 + 4:
            raise UserError(self.env._('The signature is too large. Sign again.'))
        try:
            image = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError, TypeError):
            image = b''
        if guess_mimetype(image) not in SIGNATURE_TYPES:
            raise UserError(self.env._('The signature could not be read. Sign again.'))
        return image

    # ------------------------------------------------------------------
    # The fields of a request of a template
    # ------------------------------------------------------------------

    def _field_default(self, field_type):
        """ :return: what a field of `field_type` holds when the signer does not fill it """
        self.ensure_one()
        if field_type == 'email':
            return self.partner_id.email or ''
        if field_type == 'company':
            # the company the signer works for, or theirs when the contact is a company
            commercial = self.partner_id.commercial_partner_id
            return commercial.name if commercial != self.partner_id or commercial.is_company else ''
        if field_type == 'date':
            return fields.Date.to_string(fields.Date.context_today(self))
        if field_type == 'name':
            return self.partner_id.name or ''
        return ''

    def _fields_to_fill(self):
        """ :return: the required fields of the signer that their signature and name do not fill """
        self.ensure_one()
        return self.sudo().value_ids.filtered(lambda value: value.required and value.type in ('text', 'checkbox'))

    def _signing_fields(self):
        """ :return: the fields of the signer, for the signing page """
        self.ensure_one()
        return [{**value._signing_values(), 'default': self._field_default(value.type)}
                for value in self.sudo().value_ids]

    def _others_fields(self):
        """ :return: the fields the signers who signed already filled, shown read-only on the signing page """
        self.ensure_one()
        others = self.request_id.sudo().value_ids.filtered(
            lambda value: value.signer_id != self and value.signer_id.state == 'signed' and value._is_filled())
        return [value._signed_values() for value in others]

    def _readonly_status(self):
        """ :return: what the read-only signing page tells the signer, when it shows the document with the fields
                     filled so far: 'completed', 'signed' (the others sign next) or 'waiting' (for the others
                     before them); False when the page does not show it """
        self.ensure_one()
        sign_request = self.request_id
        if sign_request.state == 'signed':
            return 'completed'
        if sign_request.state == 'sent' and self.state in ('signed', 'waiting'):
            return self.state
        return False

    def _check_field_value(self, value, raw):
        """ :return: the values to write on the field `value` filled with `raw`
            :raise UserError: when `raw` does not suit the field """
        empty = raw is None or raw is False or raw == ''
        if value.type == 'checkbox':
            if not empty and not isinstance(raw, bool):
                raise UserError(self.env._('%s is ticked or not.', value._describe()))
            if value.required and not raw:
                raise UserError(self.env._('Tick %s.', value._describe()))
            return {'value_bool': bool(raw)}
        if empty:
            if value.required:
                raise UserError(self.env._('Fill in %s.', value._describe()))
            return {'value_text': False, 'value_image': False}
        if value.type in IMAGE_TYPES:
            return {'value_image': BinaryBytes(self._decode_image(raw))}
        if not isinstance(raw, str):
            raise UserError(self.env._('%s must be a text.', value._describe()))
        text = raw.strip()
        if len(text) > TEXT_LIMIT:
            raise UserError(self.env._('%(field)s is too long: %(limit)s characters at most.',
                                       field=value._describe(), limit=TEXT_LIMIT))
        if value.type == 'date':
            try:
                if len(text) != 10:
                    raise ValueError(text)
                text = date.fromisoformat(text).isoformat()
            except ValueError:
                raise UserError(self.env._('%s must be a date.', value._describe())) from None
        elif value.type == 'email' and not single_email_re.match(text):
            raise UserError(self.env._('%s must be an email address.', value._describe()))
        if not text and value.required:
            raise UserError(self.env._('Fill in %s.', value._describe()))
        return {'value_text': text or False}

    def _sign_fields(self, values, name=None, signature=None):
        """ The signer signs, filling their fields of a request of a template.

        :param values: {id of a field of the signer (sign.request.value): value}: a base64 image (or data URI) for
                       a signature or initials, a boolean for a checkbox, a date as YYYY-MM-DD, a text otherwise.
                       The email, company and date fields left out get the signer's email, company and today.
        :param name: the name the signer signs as, by default the one of their first name field or their contact
        :param signature: the image of the certificate (bytes) when none of the fields holds one
        :raise UserError: when the signer has no fields, a field is not theirs, a required one is not filled or a
                          value does not suit """
        self.ensure_one()
        self._check_can_sign()
        if self._needs_code():
            raise UserError(self.env._('Enter the code sent to your email first.'))
        if not isinstance(values, dict):
            raise UserError(self.env._('The fields could not be read.'))
        mine = self.sudo().value_ids
        if not mine:
            raise UserError(self.env._('This document has no fields for you: sign it with your signature.'))
        given = {}
        for key, raw in values.items():
            try:
                value_id = int(key)
            except (TypeError, ValueError):
                value_id = None
            if value_id not in mine.ids:
                raise UserError(self.env._('Only your own fields can be filled in.'))
            given[value_id] = raw
        writes = []
        for value in mine:
            raw = given.get(value.id)
            if (raw is None or raw == '') and value.type in AUTO_TYPES:
                raw = self._field_default(value.type)
            writes.append((value, self._check_field_value(value, raw)))
        names = [vals['value_text'] for value, vals in writes if value.type == 'name' and vals.get('value_text')]
        # the signature of the certificate: the first one drawn, else the first initials
        images = [vals['value_image'] for field_type in IMAGE_TYPES for value, vals in writes
                  if value.type == field_type and vals.get('value_image')]
        for value, vals in writes:
            value.sudo().write(vals)
        signed_name = (name or '').strip() or (names[0] if names else self.partner_id.name)
        self._mark_signed(signed_name, images[0].content if images else signature)

    def _decline(self, reason):
        self.ensure_one()
        self._check_can_sign()
        if not (reason or '').strip():
            raise UserError(self.env._('Tell why you decline to sign.'))
        request = self.request_id
        self.sudo().write({'state': 'declined', 'decline_reason': reason.strip()})
        request.sudo().write({'state': 'declined'})
        self.env['sign.log']._log(request, 'declined', signer=self, note=reason.strip())
        request.sudo().message_post(
            body=self.env._('%(signer)s declined to sign: %(reason)s', signer=self.partner_id.name,
                            reason=reason.strip()),
            subtype_xmlid='mail.mt_note', partner_ids=request.requested_by_id.partner_id.ids)
        request._call_host('_on_sign_declined')

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_sign(self):
        """ Open the signing page, for a signer who is a user of the backend. """
        self.ensure_one()
        if not self.is_me:
            raise UserError(self.env._('Only %s signs here.', self.partner_id.name))
        return {'type': 'ir.actions.act_url', 'url': self._get_sign_url(), 'target': 'new'}

    def action_send_again(self):
        self.ensure_one()
        self._check_can_sign()
        self.request_id.check_access('write')
        self._send_invitation(reminder=True)
        return True
