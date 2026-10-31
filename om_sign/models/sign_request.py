import hashlib
import logging
import uuid
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tools import consteq, format_date
from odoo.tools.binary import BinaryBytes
from odoo.tools.image import image_data_uri
from odoo.tools.misc import hmac
from odoo.tools.pdf import merge_pdf

from .sign_template import IMAGE_TYPES
from .stamp import stamp_pdf

_logger = logging.getLogger(__name__)

# what only the signing itself changes, never a user editing the request
PROTECTED_FIELDS = {'state', 'document_hash', 'signed_hash', 'signed_attachment_id', 'date_sent', 'date_signed',
                    'access_token', 'reference', 'source', 'send_queued'}
# what a request sent keeps as it was sent
SENT_FIELDS = {'document_file', 'signer_ids', 'name', 'email_code', 'sign_template_id', 'cc_partner_ids',
               'cc_notify_sent'}
# the requests the cron sends in one run, when many are sent at once
SEND_BATCH = 50


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class SignRequest(models.Model):
    """ A document sent to people to sign: the PDF of a sign template, or a PDF uploaded.

    The signers sign in their order from a link sent by email, without logging in. Once everyone signed, the
    signed PDF is built: the document with the signatures (stamped on the fields of a template, at their places),
    followed by a certificate page listing who signed, when and from where, and the fingerprint of the document
    they were sent.
    """
    _name = 'sign.request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Signature Request'
    _check_company_auto = True
    _order = 'id desc'

    name = fields.Char(string='Document', required=True, tracking=True)
    reference = fields.Char(readonly=True, copy=False, default=lambda self: self.env._('New'))
    sign_template_id = fields.Many2one('sign.template', string='Template', ondelete='restrict',
                                       index='btree_not_null', readonly=True, check_company=True)
    res_model = fields.Char(string='Model', index=True, readonly=True)
    res_id = fields.Many2oneReference(string='Record ID', model_field='res_model', index=True, readonly=True)
    res_name = fields.Char(string='Signed For', compute='_compute_res_name')
    document_file = fields.Binary(string='PDF', attachment=True, copy=False,
                                  help='The document to sign, as it is sent to the signers.')
    document_filename = fields.Char(copy=False)
    document_hash = fields.Char(string='Document Fingerprint', readonly=True, copy=False,
                                help='SHA-256 of the document as it was sent: any change to it gives another one.')
    signed_attachment_id = fields.Many2one('ir.attachment', string='Signed PDF', readonly=True, copy=False)
    signed_hash = fields.Char(string='Signed PDF Fingerprint', readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Waiting for Signatures'),
        ('signed', 'Signed'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], required=True, default='draft', copy=False, index=True, tracking=True, readonly=True, group_expand=True)
    signer_ids = fields.One2many('sign.request.signer', 'request_id', string='Signers', copy=True)
    log_ids = fields.One2many('sign.log', 'request_id', string='Evidence', readonly=True)
    value_ids = fields.One2many('sign.request.value', 'request_id', string='Fields', readonly=True)
    signer_count = fields.Integer(compute='_compute_progress')
    signed_count = fields.Integer(compute='_compute_progress')
    progress = fields.Char(compute='_compute_progress', string='Signed')
    signer_summary = fields.Json(compute='_compute_signer_summary', string='Signers Summary',
                                 help='Each signer in their order, with their status: for the cards.')
    signer_timeline = fields.Json(compute='_compute_signer_timeline', string='Timeline',
                                  help='Each signer in their order: asked, opened, email verified, signed or '
                                       'declined, with the dates.')
    is_deadline_past = fields.Boolean(compute='_compute_is_deadline_past')
    message = fields.Text(help='Shown to the signers in the email and on the signing page.')
    email_code = fields.Boolean(
        help='Each signer gets a code by email and enters it before signing.')
    date_deadline = fields.Date(string='Sign By', tracking=True)
    reminder_days = fields.Integer(string='Remind Every', default=3,
                                   help='Days between the reminders to a signer. 0 for no reminder.')
    requested_by_id = fields.Many2one('res.users', default=lambda self: self.env.user,
                                      readonly=True, index=True)
    date_sent = fields.Datetime(string='Sent On', readonly=True, copy=False)
    date_signed = fields.Datetime(string='Completed On', readonly=True, copy=False)
    access_token = fields.Char(copy=False, readonly=True, index='btree_not_null', groups='base.group_user')
    company_id = fields.Many2one('res.company', required=True, index=True,
                                 default=lambda self: self.env.company)
    cc_partner_ids = fields.Many2many(
        'res.partner', 'sign_request_cc_partner_rel', 'request_id', 'partner_id', string='Copy To',
        help='These contacts do not sign: they are told when it is sent, and get the signed PDF.')
    cc_notify_sent = fields.Boolean(string='Tell Them When Sent', default=True,
                                    help='The copy recipients get an email when the document is sent for signature, '
                                         'not only once it is signed.')
    source = fields.Selection([
        ('send', 'Sent by a User'),
        ('bulk', 'Sent in Bulk'),
        ('share_link', 'Shared Link'),
    ], required=True, default='send', readonly=True, copy=False, index=True,
        help='How the request was made: sent by a user, one of many sent in bulk, or by a visitor of the shared '
             'link of its template.')
    send_queued = fields.Boolean(string='To Send', readonly=True, copy=False, index='btree_not_null',
                                 help='Sent in the background, with the others sent in bulk.')

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for request in self:
            record = request._get_record()
            request.res_name = record.sudo().display_name if record else False

    @api.depends('signer_ids.state')
    def _compute_progress(self):
        for request in self:
            request.signer_count = len(request.signer_ids)
            request.signed_count = len(request.signer_ids.filtered(lambda signer: signer.state == 'signed'))
            request.progress = '%s / %s' % (request.signed_count, request.signer_count)

    def _signer_values(self, signer):
        """ :return: what the cards and the timeline show of a signer """
        return {
            'id': signer.id,
            'partner_id': signer.partner_id.id,
            'name': signer.partner_id.name or '',
            'role': signer.role_name or '',
            'sequence': signer.sequence,
            'state': signer.state,
        }

    @api.depends('signer_ids.state', 'signer_ids.partner_id', 'signer_ids.role_name')
    def _compute_signer_summary(self):
        for request in self:
            request.signer_summary = [request._signer_values(signer) for signer in request.signer_ids]

    @api.depends('signer_ids.state', 'signer_ids.date_signed', 'signer_ids.date_opened', 'signer_ids.code_verified',
                 'log_ids')
    def _compute_signer_timeline(self):
        states = dict(self.env['sign.request.signer']._fields['state']._description_selection(self.env))
        # when each signer confirmed their email, and how many times they were reminded: from the evidence
        verified, reminded = {}, {}
        signers = self.signer_ids.filtered('id')
        if signers:
            for log in self.env['sign.log'].sudo().search(
                    [('signer_id', 'in', signers.ids), ('event', 'in', ('code_verified', 'reminded'))]):
                if log.event == 'code_verified':
                    verified.setdefault(log.signer_id.id, log.date)
                else:
                    reminded[log.signer_id.id] = reminded.get(log.signer_id.id, 0) + 1
        for request in self:
            request.signer_timeline = [{
                **request._signer_values(signer),
                'state_label': states.get(signer.state, ''),
                'email': signer.partner_id.email or '',
                'date_invited': fields.Datetime.to_string(signer.date_invited),
                'date_opened': fields.Datetime.to_string(signer.date_opened),
                'date_verified': fields.Datetime.to_string(verified.get(signer.id)),
                'date_signed': fields.Datetime.to_string(signer.date_signed),
                'reminders': reminded.get(signer.id, 0),
                'signed_name': signer.signed_name or '',
                'decline_reason': signer.decline_reason or '',
            } for signer in request.signer_ids]

    @api.depends('date_deadline', 'state')
    @api.depends_context('tz')
    def _compute_is_deadline_past(self):
        today = fields.Date.context_today(self)
        for request in self:
            request.is_deadline_past = request.state == 'sent' and bool(request.date_deadline) \
                and request.date_deadline < today

    def _get_record(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env or not self.res_id:
            return None
        return self.env[self.res_model].browse(self.res_id).exists() or None

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['access_token'] = uuid.uuid4().hex
            vals['reference'] = self.env['ir.sequence'].sudo().next_by_code('sign.request') or self.env._('New')
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if PROTECTED_FIELDS & set(vals):
                raise UserError(self.env._('A signature request changes as it is signed, not by hand.'))
            if any(request.state != 'draft' for request in self) and SENT_FIELDS & set(vals):
                raise UserError(self.env._('The request is sent: cancel it and send another one to change it.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_sent(self):
        if any(request.state != 'draft' for request in self):
            raise UserError(self.env._('Only a draft request can be deleted: cancel a sent one instead.'))

    # ------------------------------------------------------------------
    # Creating
    # ------------------------------------------------------------------

    @api.model
    def _create_for_record(self, record, name=None):
        """ :return: a draft request to sign a PDF about `record`, its signers suggested by the record """
        record.ensure_one()
        defaults = record._sign_default_signers() if hasattr(record, '_sign_default_signers') else []
        signers = [Command.create({'sequence': sequence, 'role_name': role, 'partner_id': partner.id})
                   for sequence, role, partner in defaults]
        company = record.company_id if 'company_id' in record._fields and record.company_id else self.env.company
        return self.create({
            'name': name or record.display_name,
            'res_model': record._name,
            'res_id': record.id,
            'signer_ids': signers,
            'company_id': company.id,
        })

    # ------------------------------------------------------------------
    # Sending and signing
    # ------------------------------------------------------------------

    def _get_document(self):
        """ :return: the bytes of the document to sign """
        self.ensure_one()
        data = self.sudo().document_file
        if not data and self.state == 'draft' and self.sign_template_id:
            data = self.sign_template_id.sudo().document_file
        return data.content if data else b''

    def action_send(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(self.env._('%s is already sent.', request.name))
            if not request.signer_ids:
                raise UserError(self.env._('Add the people signing %s.', request.name))
            missing = request.signer_ids.filtered(lambda signer: not signer.partner_id)
            if missing:
                raise UserError(self.env._('Choose who signs as %s.', missing[0].role_name or self.env._('signer')))
            no_email = request.signer_ids.filtered(lambda signer: not signer.partner_id.email)
            if no_email:
                raise UserError(self.env._('%s has no email address to receive the request.',
                                           no_email[0].partner_id.display_name))
            document = request._get_document()
            if not document:
                raise UserError(self.env._('Add the PDF to sign.'))
            request._check_document(document)
            values = {'state': 'sent', 'date_sent': fields.Datetime.now(), 'document_hash': sha256(document),
                      'send_queued': False, **request._sent_document_values(document)}
            request._create_values()
            request.sudo().write(values)
            self.env['sign.log']._log(request, 'sent', document_hash=values['document_hash'])
            request._activate_next()
            if request.state == 'sent' and request.cc_notify_sent:
                request._notify_cc_sent()
        return True

    def _check_document(self, document):
        """ Raise when `document`, the bytes of the document to sign, cannot be sent for signature. """
        self.ensure_one()
        if not document.startswith(b'%PDF'):
            raise UserError(self.env._('Only a PDF file can be sent for signature.'))

    def _sent_document_values(self, document):
        """ :return: the values keeping `document` on the request as it is sent, when it is not on it yet: the PDF
                     of the template, or of another source of the document (see _get_document) """
        self.ensure_one()
        if self.sign_template_id and not self.sudo().document_file:
            return {'document_file': BinaryBytes(document),
                    'document_filename': self.sign_template_id.document_filename}
        return {}

    def _notify_cc_sent(self):
        """ Tell the copy recipients the document is sent for signature, each with their link to follow it. """
        self.ensure_one()
        for partner in self.cc_partner_ids - self.signer_ids.partner_id:
            body = self.env['ir.qweb']._render('om_sign.mail_sign_cc_sent', {
                'sign_request': self, 'partner': partner, 'copy_url': self._get_copy_url(partner)})
            self.sudo().message_notify(
                partner_ids=partner.ids, subject=self.env._('Sent for signature: %s', self.name), body=body,
                email_layout_xmlid='mail.mail_notification_light')

    def _create_values(self):
        """ The fields of the template to fill, one per field and signer of its role, each with its own copy of
        the place of the field. """
        self.ensure_one()
        if not self.sign_template_id:
            return
        vals_list = []
        for field in self.sign_template_id.sudo().field_ids:
            signers = self.signer_ids.filtered(lambda signer: signer.template_role_id == field.role_id)
            if not signers:
                raise UserError(self.env._('Choose who signs as %s.', field.role_id.name))
            vals_list += [{
                'request_id': self.id,
                'signer_id': signer.id,
                'field_id': field.id,
                'type': field.type,
                'label': field.label,
                'required': field.required,
                'page': field.page,
                'pos_x': field.pos_x,
                'pos_y': field.pos_y,
                'width': field.width,
                'height': field.height,
            } for signer in signers]
        self.env['sign.request.value'].sudo().create(vals_list)

    def _activate_next(self):
        """ Ask the next signers, those of the lowest sequence not signed yet; complete when nobody is left. """
        self.ensure_one()
        pending = self.signer_ids.filtered(lambda signer: signer.state in ('waiting', 'to_sign'))
        if not pending:
            return self._complete()
        first = min(pending.mapped('sequence'))
        for signer in pending.filtered(lambda signer: signer.state == 'waiting' and signer.sequence == first):
            signer.sudo().write({'state': 'to_sign', 'date_invited': fields.Datetime.now()})
            signer._send_invitation()
        return True

    def _complete(self):
        """ Everyone signed: build the signed PDF and send it to everyone. """
        self.ensure_one()
        self.sudo().write({'state': 'signed', 'date_signed': fields.Datetime.now()})
        pdf = self._build_signed_pdf()
        attachment = self.env['ir.attachment'].sudo().create({
            'name': self.env._('%s (signed).pdf', (self.document_filename or self.name).removesuffix('.pdf')),
            'raw': pdf,
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.sudo().write({'signed_attachment_id': attachment.id, 'signed_hash': sha256(pdf)})
        self.env['sign.log']._log(self, 'completed', document_hash=self.signed_hash)
        partners = self.signer_ids.partner_id | self.requested_by_id.partner_id
        # from the person who sent it: the last signer is often the public user, who may not attach the PDF
        sender = self.with_user(self.requested_by_id or SUPERUSER_ID).sudo()
        sender.message_notify(
            partner_ids=partners.ids, subject=self.env._('Signed: %s', self.name), attachment_ids=attachment.ids,
            body=self.env['ir.qweb']._render('om_sign.mail_sign_completed', {'sign_request': self}),
            email_layout_xmlid='mail.mail_notification_light')
        # the copy recipients, each with their own link to the signed document
        for partner in self.cc_partner_ids - partners:
            sender.message_notify(
                partner_ids=partner.ids, subject=self.env._('Signed: %s', self.name),
                attachment_ids=attachment.ids, email_layout_xmlid='mail.mail_notification_light',
                body=self.env['ir.qweb']._render('om_sign.mail_sign_completed', {
                    'sign_request': self, 'copy_url': self._get_copy_url(partner)}))
        self.sudo().message_post(body=self.env._('Everyone signed. The signed PDF is sent to the signers.'),
                                 subtype_xmlid='mail.mt_note')
        self._call_host('_on_sign_completed')
        return True

    def _build_signed_pdf(self):
        """ :return: the document with the signatures, then the certificate page """
        self.ensure_one()
        audit = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'om_sign.action_report_sign_audit', res_ids=self.ids)[0]
        return self._merge_pdfs([self._build_signed_document(), audit])

    def _build_signed_document(self):
        """ :return: the document with the signatures: stamped on the fields of the template, or followed by a
                     signature page """
        self.ensure_one()
        if self.sign_template_id:
            return self._stamp_document()
        page = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'om_sign.action_report_sign_page', res_ids=self.ids)[0]
        return self._merge_pdfs([self._get_document(), page])

    def _stamp_document(self):
        """ :return: the PDF sent, with the values of its fields stamped at their places """
        self.ensure_one()
        items = []
        for value in self.sudo().value_ids:
            if not value._is_filled():
                continue
            if value.type in IMAGE_TYPES:
                kind, content = 'image', value.value_image.content
            elif value.type == 'checkbox':
                kind, content = 'check', True
            elif value.type == 'date':
                kind = 'text'
                content = format_date(self.env, value.value_text, lang_code=value.signer_id.partner_id.lang)
            else:
                kind, content = 'text', value.value_text
            items.append({'page': value.page, 'pos_x': value.pos_x, 'pos_y': value.pos_y, 'width': value.width,
                          'height': value.height, 'kind': kind, 'value': content})
        return stamp_pdf(self._get_document(), items)

    @api.model
    def _merge_pdfs(self, parts):
        # the reports are PDF files, except in the tests, where Odoo renders them as HTML that cannot be merged
        if all(part.startswith(b'%PDF') for part in parts):
            return merge_pdf(parts)
        return b''.join(parts)

    def action_cancel(self):
        for request in self:
            if request.state not in ('draft', 'sent'):
                raise UserError(self.env._('%s can no longer be cancelled.', request.name))
            invited = request.signer_ids.filtered(lambda signer: signer.state == 'to_sign')
            request.sudo().write({'state': 'cancelled'})
            if request.date_sent:
                self.env['sign.log']._log(request, 'cancelled')
            for signer in invited:
                signer._notify('om_sign.mail_sign_cancelled', self.env._('No longer to sign: %s', request.name))
            request._call_host('_on_sign_cancelled')
        return True

    @api.model
    def _cron_remind_and_expire(self):
        """ Expire the requests past their deadline, remind the others' signers. """
        today = fields.Date.context_today(self)
        expired = self.search([('state', '=', 'sent'), ('date_deadline', '!=', False),
                               ('date_deadline', '<', today)])
        for request in expired:
            request.sudo().write({'state': 'expired'})
            self.env['sign.log']._log(request, 'expired')
            request.sudo().message_post(
                body=self.env._('The request expired before everyone signed.'), subtype_xmlid='mail.mt_note',
                partner_ids=request.requested_by_id.partner_id.ids)
            request._call_host('_on_sign_cancelled')
        now = fields.Datetime.now()
        signers = self.env['sign.request.signer'].search([
            ('state', '=', 'to_sign'), ('request_id.state', '=', 'sent'), ('request_id.reminder_days', '>', 0)])
        for signer in signers:
            last = signer.date_reminded or signer.date_invited
            if last and last <= now - timedelta(days=signer.request_id.reminder_days):
                signer.sudo().date_reminded = now
                signer._send_invitation(reminder=True)

    @api.model
    def _cron_send_queued(self):
        """ Send the requests queued by a bulk send, as the user who sent them, a batch at a time. """
        domain = [('send_queued', '=', True), ('state', '=', 'draft')]
        cron = self.env['ir.cron']
        cron._commit_progress(remaining=self.search_count(domain))
        for request in self.search(domain, limit=SEND_BATCH, order='id'):
            user = request.requested_by_id
            try:
                with self.env.cr.savepoint():
                    request.with_user(user).with_context(allowed_company_ids=request.company_id.ids).action_send()
            except (UserError, ValidationError, AccessError) as error:
                _logger.info('Sign request %s not sent: %s', request.id, error)
                request.sudo().write({'send_queued': False})
                request.sudo().message_post(
                    body=self.env._('Not sent: %s', error), subtype_xmlid='mail.mt_note',
                    partner_ids=user.partner_id.ids)
            if not cron._commit_progress(1):
                break

    def _call_host(self, method):
        """ Tell the record signed for, when it listens (see sign.mixin). """
        record = self._get_record()
        if record is not None and hasattr(record, method):
            getattr(record, method)(self)

    # ------------------------------------------------------------------
    # Printing
    # ------------------------------------------------------------------

    @api.model
    def _signer_entries(self, signers):
        """ :return: what the signature block of each signer shows, for `om_sign.signature_blocks` """
        return [{
            'name': signer.signed_name or signer.partner_id.name,
            'role': signer.role_name,
            'signature': signer.signature,
            'date': signer.date_signed,
        } for signer in signers]

    @api.model
    def _render_signature_blocks(self, entries):
        return self.env['ir.qweb']._render('om_sign.signature_blocks', {
            'entries': entries, 'image_data_uri': image_data_uri})

    def _get_verify_url(self):
        self.ensure_one()
        return '%s/sign/verify/%s' % (self.get_base_url(), self.sudo().access_token)

    # ------------------------------------------------------------------
    # The copy recipients
    # ------------------------------------------------------------------

    def _get_copy_token(self, partner):
        """ :return: the secret of the link of a copy recipient, theirs only, for this request only """
        self.ensure_one()
        return hmac(self.env(su=True), 'om_sign-copy', (self.id, partner.id, self.sudo().access_token))

    def _check_copy_token(self, partner, token):
        self.ensure_one()
        return bool(token) and partner in self.sudo().cc_partner_ids and consteq(self._get_copy_token(partner), token)

    def _get_copy_url(self, partner):
        self.ensure_one()
        return '%s/sign/copy/%s/%s/%s' % (self.get_base_url(), self.id, partner.id, self._get_copy_token(partner))

    def _shown_values(self):
        """ :return: the fields filled so far, by the signers who signed, as the read-only page shows them; none once
                     everyone signed: the signed PDF holds them """
        self.ensure_one()
        if self.state == 'signed':
            return []
        values = self.sudo().value_ids.filtered(
            lambda value: value.signer_id.state == 'signed' and value._is_filled())
        return [value._signed_values() for value in values]

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_download_signed(self):
        self.ensure_one()
        if not self.signed_attachment_id:
            raise UserError(self.env._('%s is not signed by everyone yet.', self.name))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self.signed_attachment_id.id,
            'target': 'download',
        }

    def action_open_signed_pdf(self):
        """ The signed PDF, in the browser. """
        self.ensure_one()
        if not self.signed_attachment_id:
            raise UserError(self.env._('%s is not signed by everyone yet.', self.name))
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s' % self.signed_attachment_id.id,
                'target': 'new'}

    def action_open_template(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sign.template',
            'res_id': self.sign_template_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    @api.model
    def action_open_landing(self):
        """ Sign, opened from the home menu: all the requests for an administrator, the documents to sign for the
        others. """
        xmlid = 'om_sign.sign_request_action' if self.env.user.has_group('om_sign.group_sign_manager') \
            else 'om_sign.sign_request_action_to_sign'
        return self.env['ir.actions.act_window']._for_xml_id(xmlid)

    def _get_open_record(self):
        """ :return: the record the Record button opens """
        self.ensure_one()
        return self._get_record()

    def action_open_record(self):
        self.ensure_one()
        record = self._get_open_record()
        if not record:
            raise UserError(self.env._('The record of %s no longer exists.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
