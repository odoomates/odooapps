from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import html2plaintext
from odoo.tools.misc import human_size
from odoo.tools.binary import BinaryBytes


class DocumentsDocument(models.Model):
    """ A document: a file, or a link, in a folder. The file is an attachment of the document; a new version of it
    keeps the previous one in the history of the document, from which it can be restored.

    A document may stand for a record of another model (``res_model``, ``res_id``), e.g. the vendor bill made from
    it. A request is a document without its file yet, asked to a contact who uploads it from a link.
    """
    _name = 'om.documents.document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Document'
    _order = 'id desc'
    _mail_post_access = 'read'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True, index='trigram')
    active = fields.Boolean(default=True, tracking=True)
    folder_id = fields.Many2one('om.documents.folder', string='Folder', required=True, index=True, tracking=True,
                                ondelete='restrict', default=lambda self: self._default_folder(),
                                check_company=True)
    company_id = fields.Many2one(related='folder_id.company_id', store=True, index=True)
    type = fields.Selection([('binary', 'File'), ('url', 'Link')], required=True, default='binary')
    attachment_id = fields.Many2one('ir.attachment', string='Attachment', index='btree_not_null', copy=False,
                                    ondelete='set null', readonly=True)
    datas = fields.Binary(string='File', compute='_compute_datas', inverse='_inverse_datas', attachment=False)
    file_name = fields.Char(string='File Name', copy=False)
    mimetype = fields.Char(related='attachment_id.mimetype', store=True, string='File Type')
    file_size = fields.Integer(related='attachment_id.file_size', store=True, string='Size')
    file_size_human = fields.Char(string='File Size', compute='_compute_file_size_human')
    checksum = fields.Char(related='attachment_id.checksum', string='Checksum')
    file_extension = fields.Char(compute='_compute_file_extension', string='Extension')
    url = fields.Char(string='Link', tracking=True)
    description = fields.Text()
    owner_id = fields.Many2one('res.users', string='Owner', default=lambda self: self.env.user, index=True,
                               tracking=True, domain=[('share', '=', False)])
    partner_id = fields.Many2one('res.partner', string='Contact', index='btree_not_null', tracking=True)
    tag_ids = fields.Many2many('om.documents.tag', 'om_documents_document_tag_rel', 'document_id', 'tag_id',
                               string='Tags')
    allowed_tag_ids = fields.Many2many('om.documents.tag', compute='_compute_allowed_tag_ids')

    # the record the document stands for
    res_model = fields.Char(string='Linked Model', index=True, copy=False)
    res_id = fields.Many2oneReference(string='Linked Record ID', model_field='res_model', index=True, copy=False)
    res_name = fields.Char(string='Linked To', compute='_compute_res_name')
    record_ref = fields.Reference(selection='_selection_record_ref', string='Linked Record',
                                  compute='_compute_record_ref', inverse='_inverse_record_ref')

    version_ids = fields.One2many('om.documents.version', 'document_id', string='Versions')
    version_count = fields.Integer(compute='_compute_version_count', string='Previous Versions')
    lock_uid = fields.Many2one('res.users', string='Locked By', readonly=True, copy=False, tracking=True)
    is_locked = fields.Boolean(compute='_compute_is_locked')
    favorited_user_ids = fields.Many2many('res.users', 'om_documents_document_favorite_rel', 'document_id',
                                          'user_id', string='Starred By', copy=False)
    is_favorite = fields.Boolean(string='Starred', compute='_compute_is_favorite', inverse='_inverse_is_favorite',
                                 search='_search_is_favorite')

    # requests
    is_request = fields.Boolean(string='Requested', copy=False, readonly=True,
                                help='Asked to the contact, who uploads the file from the link sent to them.')
    request_deadline = fields.Date(string='Requested By', copy=False, tracking=True)
    request_state = fields.Selection([('missing', 'Missing'), ('received', 'Received')], string='Request Status',
                                     compute='_compute_request_state', store=True, index='btree_not_null')

    # ------------------------------------------------------------------
    # Defaults and computes
    # ------------------------------------------------------------------

    @api.model
    def _default_folder(self):
        folder = self.env['om.documents.folder'].browse(self.env.context.get('om_documents_folder_id'))
        if folder.exists():
            return folder
        if self.env.user._is_internal():
            return self.env['om.documents.folder']._get_my_drive()
        return self.env['om.documents.folder']

    @api.depends('attachment_id')
    def _compute_datas(self):
        for document in self:
            document.datas = document.attachment_id.raw if document.attachment_id else False

    def _inverse_datas(self):
        for document in self:
            if not document.datas:
                continue
            attachment = self.env['ir.attachment'].create({
                'name': document.file_name or document.name,
                'raw': document.datas,
                'res_model': self._name,
                'res_id': document.id,
            })
            document._set_file(attachment)

    @api.depends('file_size')
    def _compute_file_size_human(self):
        for document in self:
            document.file_size_human = human_size(document.file_size)

    @api.depends('file_name', 'attachment_id.name')
    def _compute_file_extension(self):
        for document in self:
            name = document.file_name or document.attachment_id.name or ''
            document.file_extension = name.rsplit('.', 1)[1].lower() if '.' in name else False

    @api.depends('folder_id')
    def _compute_allowed_tag_ids(self):
        Tag = self.env['om.documents.tag']
        for document in self:
            document.allowed_tag_ids = Tag.search(Tag._domain_for_folder(document.folder_id))

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for document in self:
            record = document._get_record()
            document.res_name = record.sudo().display_name if record else False

    @api.model
    def _selection_record_ref(self):
        models_ = self.env['ir.model'].sudo().search([('transient', '=', False), ('is_mail_thread', '=', True)])
        return [(model.model, model.name) for model in models_ if model.model != self._name]

    @api.depends('res_model', 'res_id')
    def _compute_record_ref(self):
        for document in self:
            record = document._get_record()
            document.record_ref = '%s,%s' % (record._name, record.id) if record else False

    def _inverse_record_ref(self):
        for document in self:
            if document.record_ref:
                document.write({'res_model': document.record_ref._name, 'res_id': document.record_ref.id})
            else:
                document.write({'res_model': False, 'res_id': False})

    def _compute_version_count(self):
        counts = dict(self.env['om.documents.version']._read_group(
            [('document_id', 'in', self.ids)], ['document_id'], ['__count']))
        for document in self:
            document.version_count = counts.get(document, 0)

    @api.depends('lock_uid')
    def _compute_is_locked(self):
        for document in self:
            document.is_locked = bool(document.lock_uid) and document.lock_uid != self.env.user

    @api.depends('favorited_user_ids')
    @api.depends_context('uid')
    def _compute_is_favorite(self):
        for document in self:
            document.is_favorite = self.env.user in document.favorited_user_ids

    def _inverse_is_favorite(self):
        # starring is personal: who reads a document stars it, even in a folder they only read
        for document in self:
            command = Command.link if document.is_favorite else Command.unlink
            document.sudo().favorited_user_ids = [command(self.env.uid)]

    def _search_is_favorite(self, operator, value):
        if operator != 'in':
            return NotImplemented
        if True in value and False not in value:
            return Domain('favorited_user_ids', 'in', self.env.uid)
        if False in value and True not in value:
            return Domain('favorited_user_ids', 'not in', self.env.uid)
        return Domain.TRUE

    @api.depends('is_request', 'attachment_id', 'type', 'url')
    def _compute_request_state(self):
        for document in self:
            if not document.is_request:
                document.request_state = False
            elif document.attachment_id or (document.type == 'url' and document.url):
                document.request_state = 'received'
            else:
                document.request_state = 'missing'

    def _get_record(self):
        """ :return: the record the document stands for, None when it has none or it no longer exists """
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env or not self.res_id:
            return None
        return self.env[self.res_model].browse(self.res_id).exists() or None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        attachments = self.env['ir.attachment']
        for vals in vals_list:
            if vals.get('record_ref'):
                model, res_id = vals.pop('record_ref').split(',')
                vals.update(res_model=model, res_id=int(res_id))
            attachment = attachments.browse(vals.get('attachment_id'))
            if attachment:
                vals.setdefault('file_name', attachment.name)
                vals.setdefault('name', attachment.name)
            if not vals.get('name'):
                vals['name'] = vals.get('file_name') or vals.get('url') or self.env._('New Document')
            if vals.get('url') and not vals.get('datas') and not attachment:
                vals.setdefault('type', 'url')
        documents = super().create(vals_list)
        for document in documents.filtered('attachment_id'):
            document.attachment_id._om_documents_claim(document)
        return documents

    def write(self, vals):
        if not self.env.su and set(vals) - {'is_favorite', 'favorited_user_ids'}:
            locked = self.filtered('is_locked')
            if locked and not self.env.user.has_group('om_documents.group_documents_manager'):
                raise UserError(self.env._('%(document)s is locked by %(user)s.', document=locked[0].name,
                                           user=locked[0].lock_uid.name))
        if vals.get('folder_id') and not self.env.su:
            self.env['om.documents.folder'].browse(vals['folder_id']).check_access('write')
        return super().write(vals)

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for document, vals in zip(self, vals_list):
            vals['name'] = self.env._('%s (copy)', document.name)
            if document.attachment_id and 'datas' not in (default or {}):
                vals['datas'] = document.attachment_id.raw
                vals['file_name'] = document.file_name
        return vals_list

    # ------------------------------------------------------------------
    # Files and versions
    # ------------------------------------------------------------------

    def _set_file(self, attachment, version_note=None):
        """ Make `attachment` the file of the document, the file it had going to its versions. """
        self.ensure_one()
        attachment._om_documents_claim(self)
        previous = self.attachment_id
        if previous and previous != attachment:
            self.env['om.documents.version'].sudo().create({
                'document_id': self.id,
                'attachment_id': previous.id,
                'note': version_note,
            })
        was_missing = self.request_state == 'missing'
        self.write({
            'attachment_id': attachment.id,
            'file_name': attachment.name,
            'type': 'binary',
        })
        if previous and previous != attachment:
            self.message_post(body=self.env._('New version: %(new)s replaces %(old)s.', new=attachment.name,
                                              old=previous.name), subtype_xmlid='mail.mt_note')
        if was_missing:
            self._on_request_received()

    def _restore_version(self, version):
        self.ensure_one()
        attachment = version.attachment_id
        version.sudo().unlink()
        self._set_file(attachment, version_note=self.env._('Replaced by the restored %s', attachment.name))

    def _get_raw(self):
        """ :return: the bytes of the file of the document, b'' for a link or a missing file """
        self.ensure_one()
        raw = self.attachment_id.sudo().raw
        return raw.content if raw else b''

    @api.model
    def upload_files(self, folder_id, files, values=None):
        """ Documents from files dropped in the browser.

        :param folder_id: the folder to upload in, the My Drive of the user when False
        :param files: a list of dicts: name, mimetype, data (base64)
        :param values: more values of the documents, e.g. their tags
        :return: the ids of the documents
        """
        folder = self.env['om.documents.folder'].browse(folder_id) if folder_id \
            else self.env['om.documents.folder']._get_my_drive()
        folder.check_access('write')
        documents = self.create([{
            **(values or {}),
            'name': file['name'],
            'file_name': file['name'],
            'folder_id': folder.id,
            'datas': file['data'],
        } for file in files])
        return documents.ids

    def upload_version(self, file):
        """ A new version of the document from a file dropped in the browser: a dict name, mimetype, data. """
        self.ensure_one()
        self.check_access('write')
        self.write({'file_name': file['name'], 'datas': file['data']})
        return True

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    def _on_request_received(self):
        """ The file of a request arrived: the activity of the request is done. """
        for document in self:
            activities = document.activity_ids.filtered(
                lambda a: a.activity_type_id == self.env.ref('om_documents.mail_activity_type_request',
                                                             raise_if_not_found=False))
            activities.sudo().action_feedback(feedback=self.env._('The document is received.'))
            document.message_post(body=self.env._('The requested document is received.'),
                                  subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------
    # Upload by email
    # ------------------------------------------------------------------

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """ A document from each file of an email sent to the alias of a folder, its sender as their contact. """
        values = dict(custom_values or {})
        partner = self.env['res.partner'].browse(msg_dict.get('author_id')).exists()
        if partner:
            values.setdefault('partner_id', partner.id)
        subject = msg_dict.get('subject') or self.env._('Emailed Document')
        files = msg_dict.get('attachments') or []
        vals_list = []
        for attachment in files:
            name, content = attachment[0], attachment[1]
            if isinstance(content, str):
                content = content.encode()
            vals_list.append({
                **values,
                'name': name,
                'file_name': name,
                'datas': BinaryBytes(content),
                'description': subject,
            })
        if not vals_list:
            body = html2plaintext(msg_dict.get('body') or '')
            vals_list.append({**values, 'name': subject, 'description': body or False})
        documents = self.create(vals_list)
        # the files are the documents: the email is posted on the first one, without them
        msg_dict['attachments'] = []
        for document in documents[1:]:
            document.message_post(body=self.env._('Received by email from %(sender)s: %(subject)s',
                                                  sender=msg_dict.get('email_from') or '', subject=subject),
                                  subtype_xmlid='mail.mt_note')
        return documents[:1]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_lock(self):
        for document in self:
            if document.lock_uid and document.lock_uid != self.env.user and \
                    not self.env.user.has_group('om_documents.group_documents_manager'):
                raise UserError(self.env._('%(document)s is locked by %(user)s.', document=document.name,
                                           user=document.lock_uid.name))
            document.sudo().lock_uid = False if document.lock_uid else self.env.user
        return True

    def action_toggle_favorite(self):
        for document in self:
            document.is_favorite = not document.is_favorite
        return True

    def action_download(self):
        documents = self.filtered('attachment_id')
        if not documents:
            raise UserError(self.env._('Nothing to download: the documents have no file.'))
        if len(documents) == 1:
            url = '/web/content/%s?download=true' % documents.attachment_id.id
        else:
            url = '/om_documents/zip?ids=%s' % ','.join(str(i) for i in documents.ids)
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'download'}

    def action_share(self):
        if not self:
            raise UserError(self.env._('Select the documents to share.'))
        share = self.env['om.documents.share'].create({
            'share_type': 'documents',
            'document_ids': [Command.set(self.ids)],
            'folder_id': self[:1].folder_id.id,
        })
        return share._action_open()

    def action_open_record(self):
        self.ensure_one()
        record = self._get_record()
        if not record:
            raise UserError(self.env._('%s is linked to no record.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_open_versions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Versions of %s', self.name),
            'res_model': 'om.documents.version',
            'view_mode': 'list',
            'domain': [('document_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_move(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Move or Tag'),
            'res_model': 'om.documents.move.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_ids': self.ids},
        }

    def action_run_actions(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Run an Action'),
            'res_model': 'om.documents.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_ids': self.ids},
        }

    def _get_viewer_data(self):
        """ :return: what the file viewer shows of each document """
        return [{
            'id': document.attachment_id.id,
            'name': document.file_name or document.name,
            'mimetype': document.mimetype,
            'checksum': document.checksum,
            'type': 'url' if document.type == 'url' else 'binary',
            'url': document.url,
        } for document in self]

    def get_viewer_data(self):
        return self._get_viewer_data()

    # ------------------------------------------------------------------
    # Records from documents
    # ------------------------------------------------------------------

    def _attach_to(self, record):
        """ Attach a copy of the file of the document to `record`, linked to the document. """
        self.ensure_one()
        attachment = self.env['ir.attachment']
        if self.attachment_id:
            attachment = self.attachment_id.sudo().with_context(om_documents_no_sync=True).copy({
                'res_model': record._name,
                'res_id': record.id,
            })
        self.write({'res_model': record._name, 'res_id': record.id})
        return attachment

    def _create_record(self, model, binary_field=None):
        """ :return: a record of `model` made from the document: its name, its contact, its file attached and,
                     when `binary_field` is given, in that field """
        self.ensure_one()
        Model = self.env[model]
        values = {}
        rec_name = Model._rec_name
        if rec_name and rec_name in Model._fields and Model._fields[rec_name].type in ('char', 'text') \
                and not Model._fields[rec_name].compute:
            values[rec_name] = self.name
        if self.partner_id and 'partner_id' in Model._fields and Model._fields['partner_id'].type == 'many2one' \
                and Model._fields['partner_id'].comodel_name == 'res.partner':
            values['partner_id'] = self.partner_id.id
        if binary_field and self.attachment_id:
            values[binary_field] = self.attachment_id.sudo().raw
        record = Model.with_context(om_documents_no_sync=True).create(values)
        attachment = self._attach_to(record)
        if attachment and hasattr(record, 'message_post'):
            record.message_post(body=self.env._('Created from the document %s.', self.name),
                                attachment_ids=attachment.ids)
            if 'message_main_attachment_id' in record._fields and not record.message_main_attachment_id:
                record.sudo().message_main_attachment_id = attachment
        return record

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        if field_name == 'folder_id' and self.env.user._is_internal():
            # the folder panel always offers the My Drive of the user
            self.env['om.documents.folder']._get_my_drive()
        return super().search_panel_select_range(field_name, **kwargs)

    # ------------------------------------------------------------------
    # Hooks for the bridges
    # ------------------------------------------------------------------

    @api.model
    def _get_record_folder(self, record):
        """ :return: the folder of the documents of `record`, empty when its model keeps none (see
                     om.documents.mixin) """
        if hasattr(record, '_get_documents_folder'):
            return record._get_documents_folder()
        return self.env['om.documents.folder']
