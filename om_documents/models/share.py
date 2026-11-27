import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


class DocumentsShare(models.Model):
    """ A link to documents for people without access to them: a folder, or chosen documents, with an expiry date.
    An upload link lets them add files to the folder, e.g. a customer sending their papers. Each visit, download
    and upload is logged. """
    _name = 'om.documents.share'
    _inherit = ['mail.thread']
    _description = 'Document Share'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(compute='_compute_name', store=True, readonly=False, required=True, precompute=True)
    share_type = fields.Selection([
        ('folder', 'A Folder'),
        ('documents', 'Chosen Documents'),
    ], string='Share', required=True, default='documents')
    folder_id = fields.Many2one('om.documents.folder', string='Folder', index=True, ondelete='cascade',
                                check_company=True)
    include_subfolders = fields.Boolean(string='With Subfolders')
    document_ids = fields.Many2many('om.documents.document', 'om_documents_share_document_rel', 'share_id',
                                    'document_id', string='Documents')
    access_token = fields.Char(required=True, copy=False, readonly=True, index=True,
                               default=lambda self: uuid.uuid4().hex, groups='om_documents.group_documents_user')
    full_url = fields.Char(string='Link', compute='_compute_full_url')
    date_expiry = fields.Date(string='Valid Until', tracking=True, default=lambda self: self._default_date_expiry(),
                              help='Leave empty for a link that never expires.')
    state = fields.Selection([('live', 'Live'), ('expired', 'Expired')], compute='_compute_state',
                             search='_search_state')
    active = fields.Boolean(default=True, tracking=True, help='Archive the share to close the link.')
    allow_download = fields.Boolean(string='Download', default=True,
                                    help='The visitors download the files, one by one or all of them as a zip.')
    allow_upload = fields.Boolean(string='Upload', help='The visitors upload files into the folder.')
    upload_tag_ids = fields.Many2many('om.documents.tag', 'om_documents_share_upload_tag_rel', 'share_id', 'tag_id',
                                      string='Tags of Uploads')
    upload_owner_id = fields.Many2one('res.users', string='Owner of Uploads', default=lambda self: self.env.user,
                                      domain=[('share', '=', False)])
    partner_ids = fields.Many2many('res.partner', 'om_documents_share_partner_rel', 'share_id', 'partner_id',
                                   string='Shared With',
                                   help='These contacts find the share in their portal, and receive it by email.')
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    log_ids = fields.One2many('om.documents.share.log', 'share_id', string='Access Log')
    log_count = fields.Integer(compute='_compute_log_count', string='Visits')
    document_count = fields.Integer(compute='_compute_document_count', string='Shared Documents')
    request_document_id = fields.Many2one(
        'om.documents.document', string='Requested Document', index='btree_not_null', ondelete='cascade',
        help='The upload fills this requested document.')

    @api.model
    def _default_date_expiry(self):
        days = self.env.company.om_documents_share_days
        return fields.Date.add(fields.Date.context_today(self), days=days) if days > 0 else False

    @api.depends('share_type', 'folder_id', 'document_ids')
    def _compute_name(self):
        for share in self:
            if share.name:
                continue
            if share.share_type == 'folder' and share.folder_id:
                share.name = share.folder_id.name
            elif len(share.document_ids) == 1:
                share.name = share.document_ids.name
            elif share.document_ids:
                share.name = self.env._('%s documents', len(share.document_ids))
            else:
                share.name = self.env._('Shared Documents')

    def _compute_full_url(self):
        base_url = self.get_base_url()
        for share in self:
            share.full_url = '%s/documents/share/%s/%s' % (base_url, share.id, share.sudo().access_token) \
                if share.id else False

    @api.depends('date_expiry', 'active')
    @api.depends_context('date')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for share in self:
            share.state = 'expired' if not share.active or (share.date_expiry and share.date_expiry < today) \
                else 'live'

    def _search_state(self, operator, value):
        if operator != 'in':
            return NotImplemented
        today = fields.Date.context_today(self)
        live = Domain('active', '=', True) & (Domain('date_expiry', '=', False) | Domain('date_expiry', '>=', today))
        domains = []
        if 'live' in value:
            domains.append(live)
        if 'expired' in value:
            domains.append(~live)
        return Domain.OR(domains) if domains else Domain.FALSE

    def _compute_log_count(self):
        counts = dict(self.env['om.documents.share.log']._read_group(
            [('share_id', 'in', self.ids)], ['share_id'], ['__count']))
        for share in self:
            share.log_count = counts.get(share, 0)

    def _compute_document_count(self):
        for share in self:
            share.document_count = len(share.sudo()._get_documents())

    @api.constrains('share_type', 'folder_id', 'allow_upload')
    def _check_folder(self):
        for share in self:
            if (share.share_type == 'folder' or share.allow_upload) and not share.folder_id:
                raise ValidationError(self.env._('Choose the folder of the share %s.', share.name))

    @api.model_create_multi
    def create(self, vals_list):
        shares = super().create(vals_list)
        if not self.env.su:
            # a user shares what they reach only
            for share in shares:
                share.document_ids.check_access('read')
                if share.folder_id:
                    share.folder_id.check_access('write' if share.allow_upload else 'read')
        return shares

    def write(self, vals):
        result = super().write(vals)
        if not self.env.su and {'document_ids', 'folder_id', 'allow_upload'} & set(vals):
            for share in self:
                share.document_ids.check_access('read')
                if share.folder_id:
                    share.folder_id.check_access('write' if share.allow_upload else 'read')
        return result

    # ------------------------------------------------------------------
    # Public side (called as the super user, after checking the token)
    # ------------------------------------------------------------------

    def _get_documents(self):
        """ :return: the documents reached by the link """
        self.ensure_one()
        Document = self.env['om.documents.document']
        if self.share_type == 'folder':
            folders = self.folder_id._get_descendants() if self.include_subfolders else self.folder_id
            documents = Document.search([('folder_id', 'in', folders.ids)])
        else:
            documents = self.document_ids.filtered('active')
        return documents.filtered(lambda d: d.attachment_id or (d.type == 'url' and d.url))

    def _check_live(self):
        self.ensure_one()
        return self.state == 'live'

    def _log(self, event, document=None, request=None):
        values = {'share_id': self.id, 'event': event, 'document_id': document.id if document else False}
        if request is not None:
            values['ip_address'] = request.httprequest.remote_addr
            values['partner_id'] = request.env.user.partner_id.id if not request.env.user._is_public() else False
        self.env['om.documents.share.log'].sudo().create(values)

    def _upload(self, files, partner=None):
        """ Documents in the folder from the files a visitor uploaded: a list of (name, mimetype, bytes) """
        self.ensure_one()
        if not self.allow_upload or not self._check_live():
            raise UserError(self.env._('This link takes no upload.'))
        Document = self.env['om.documents.document'].sudo()
        documents = Document
        for name, mimetype, raw in files:
            attachment = self.env['ir.attachment'].sudo().create({
                'name': name, 'raw': raw, 'mimetype': mimetype or False,
                'res_model': Document._name, 'res_id': 0,
            })
            request_document = self.request_document_id
            if request_document and request_document.request_state == 'missing':
                request_document._set_file(attachment)
                documents |= request_document
                continue
            documents |= Document.create({
                'name': name,
                'folder_id': self.folder_id.id,
                'attachment_id': attachment.id,
                'owner_id': self.upload_owner_id.id or self.create_uid.id,
                'partner_id': (partner or self.partner_ids[:1]).id,
                'tag_ids': [fields.Command.set(self.upload_tag_ids.ids)],
            })
        if documents:
            self.message_post(body=self.env._('%(count)s files uploaded: %(names)s', count=len(files),
                                              names=', '.join(documents.mapped('name'))),
                              partner_ids=self.upload_owner_id.partner_id.ids)
        return documents

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _action_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Share'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('om_documents.om_documents_share_view_form_dialog').id, 'form')],
            'target': 'new',
        }

    def action_send(self):
        self.ensure_one()
        if not self.partner_ids:
            raise UserError(self.env._('Choose who the documents are shared with.'))
        template = self.env.ref('om_documents.mail_template_share')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_model': self._name,
                'default_res_ids': self.ids,
                'default_template_id': template.id,
                'default_composition_mode': 'comment',
                'default_partner_ids': self.partner_ids.ids,
            },
        }

    def action_open_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Access Log'),
            'res_model': 'om.documents.share.log',
            'view_mode': 'list',
            'domain': [('share_id', '=', self.id)],
        }

    def action_open_share(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.full_url, 'target': 'new'}

    def action_regenerate_token(self):
        for share in self:
            share.sudo().access_token = uuid.uuid4().hex
        return True


class DocumentsShareLog(models.Model):
    _name = 'om.documents.share.log'
    _description = 'Document Share Access'
    _order = 'id desc'
    _rec_name = 'event'

    share_id = fields.Many2one('om.documents.share', string='Share', required=True, index=True, ondelete='cascade')
    event = fields.Selection([
        ('view', 'Opened'),
        ('download', 'Downloaded'),
        ('download_all', 'Downloaded All'),
        ('upload', 'Uploaded'),
        ('expired', 'Refused: Expired'),
    ], required=True)
    document_id = fields.Many2one('om.documents.document', string='Document', ondelete='set null')
    partner_id = fields.Many2one('res.partner', string='Visitor')
    ip_address = fields.Char(string='IP Address')
