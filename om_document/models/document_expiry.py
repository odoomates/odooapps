import base64
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools.misc import format_date


class DocumentsDocument(models.Model):
    """ A document with an expiry: a type, a number, an issue and an expiry date, reminders and renewals.

    Its holder is the record the document is linked to (``res_model``, ``res_id``), e.g. the employee holding a
    passport; a model inheriting ``om.documents.expiry.mixin`` names who is reminded and who holds the documents.
    The main file is the file of the document; more files, e.g. the back of an identity card, are its extra files.
    """
    _inherit = 'om.documents.document'

    type_id = fields.Many2one(
        'om.documents.type', string='Document Type', tracking=True, index='btree_not_null', ondelete='set null',
        domain="['|', ('res_model', '=', False), ('res_model', '=', res_model)]",
        help='Tracks the expiry of the document: its number, its dates and its reminders.')
    has_number = fields.Boolean(related='type_id.has_number')
    has_issue_date = fields.Boolean(related='type_id.has_issue_date')
    has_expiry_date = fields.Boolean(related='type_id.has_expiry_date')
    type_res_model = fields.Char(related='type_id.res_model', string='Type Model')
    number = fields.Char(tracking=True, index='btree_not_null')
    date_issue = fields.Date(string='Issued On', tracking=True)
    date_expiry = fields.Date(string='Expires On', tracking=True, index='btree_not_null')
    country_id = fields.Many2one('res.country', string='Issued By')
    extra_attachment_ids = fields.Many2many(
        'ir.attachment', 'om_documents_document_extra_attachment_rel', 'document_id', 'attachment_id',
        string='Extra Files', copy=False,
        help='More files of the document, e.g. the back of an identity card. The main file stays the file of the '
             'document.')
    file_count = fields.Integer(string='Files', compute='_compute_expiry_preview')
    expiry_preview_url = fields.Char(compute='_compute_expiry_preview')
    expiry_state = fields.Selection([
        ('none', 'No Expiry'),
        ('valid', 'Valid'),
        ('expiring', 'Expiring'),
        ('expired', 'Expired'),
    ], string='Expiry', compute='_compute_expiry_state', search='_search_expiry_state',
        help='Expiring: the first reminder of its type is due.')
    days_left = fields.Integer(compute='_compute_expiry_state')
    last_reminder = fields.Integer(
        copy=False, default=-1,
        help='The reminder sent last, in days before the expiry date, -1 for none: each one is sent once.')
    previous_id = fields.Many2one('om.documents.document', string='Renews', copy=False, readonly=True,
                                  index='btree_not_null', ondelete='set null')
    renewal_ids = fields.One2many('om.documents.document', 'previous_id', string='Renewals',
                                  context={'active_test': False})
    next_id = fields.Many2one('om.documents.document', string='Renewed By', compute='_compute_next_id')

    # ------------------------------------------------------------------
    # Computes and checks
    # ------------------------------------------------------------------

    @api.depends('attachment_id', 'mimetype', 'extra_attachment_ids')
    def _compute_expiry_preview(self):
        for document in self:
            files = document.attachment_id | document.extra_attachment_ids
            images = files.filtered(lambda a: (a.mimetype or '').startswith('image/'))
            document.expiry_preview_url = '/web/image/%s/320x200' % images[0].id if images else False
            document.file_count = len(files)

    @api.depends('date_expiry', 'type_id.has_expiry_date', 'type_id.reminder_days')
    @api.depends_context('date')
    def _compute_expiry_state(self):
        today = fields.Date.context_today(self)
        for document in self:
            if not document.date_expiry or not document.type_id.has_expiry_date:
                document.expiry_state, document.days_left = 'none', 0
                continue
            document.days_left = (document.date_expiry - today).days
            if document.days_left < 0:
                document.expiry_state = 'expired'
            elif document.days_left <= max(document.type_id._get_reminder_days() or [0]):
                document.expiry_state = 'expiring'
            else:
                document.expiry_state = 'valid'

    def _search_expiry_state(self, operator, value):
        if operator != 'in':
            return NotImplemented
        today = fields.Date.context_today(self)
        expiring = Domain.FALSE
        for doc_type in self.env['om.documents.type'].sudo().with_context(active_test=False).search(
                [('has_expiry_date', '=', True)]):
            horizon = today + timedelta(days=max(doc_type._get_reminder_days() or [0]))
            expiring |= Domain('type_id', '=', doc_type.id) & Domain('date_expiry', '>=', today) \
                & Domain('date_expiry', '<=', horizon)
        expires = Domain('type_id.has_expiry_date', '=', True)
        domains = {
            'none': Domain('date_expiry', '=', False) | Domain('type_id', '=', False)
                    | Domain('type_id.has_expiry_date', '=', False),
            'expired': Domain('date_expiry', '<', today) & expires,
            'expiring': expiring,
            'valid': Domain('date_expiry', '>=', today) & expires & ~expiring,
        }
        return Domain.OR(domains[state] for state in value if state in domains)

    @api.depends('renewal_ids')
    def _compute_next_id(self):
        for document in self:
            document.next_id = document.with_context(active_test=False).renewal_ids[:1]

    @api.constrains('date_issue', 'date_expiry')
    def _check_expiry_dates(self):
        for document in self:
            if document.date_issue and document.date_expiry and document.date_expiry < document.date_issue:
                raise ValidationError(self.env._('%s expires before it is issued.', document.name))

    @api.constrains('res_model', 'type_id', 'company_id')
    def _check_expiry_type(self):
        for document in self:
            if document.type_id.res_model and document.type_id.res_model != document.res_model:
                raise ValidationError(self.env._(
                    'A %(type)s is kept on a %(model)s: link %(document)s to one.', type=document.type_id.name,
                    model=self.env['ir.model']._get(document.type_id.res_model).name, document=document.name))
            company = document.type_id.company_id
            if company and document.company_id and company != document.company_id:
                raise ValidationError(self.env._(
                    '%(type)s belongs to %(company)s: %(document)s cannot be of it.', type=document.type_id.name,
                    company=company.name, document=document.name))

    @api.onchange('type_id', 'number')
    def _onchange_expiry_name(self):
        if not self.type_id:
            return
        type_names = self.env['om.documents.type'].sudo().with_context(active_test=False).search([]).mapped('name')
        if not self.name or self.name == self.env._('New Document') \
                or any(self.name.startswith(name) for name in type_names):
            self.name = self._get_expiry_name(self.type_id, self.number)

    @api.onchange('record_ref')
    def _onchange_record_ref(self):
        if self.record_ref:
            self.res_model, self.res_id = self.record_ref._name, self.record_ref.id

    @api.onchange('type_id', 'record_ref')
    def _onchange_expiry_folder(self):
        if self.type_id and (not self.folder_id or self.folder_id.is_private):
            self.folder_id = self._get_expiry_folder(self.type_id, self.record_ref or None) or self.folder_id

    # ------------------------------------------------------------------
    # Holder, folder and name
    # ------------------------------------------------------------------

    @api.model
    def _get_expiry_name(self, doc_type, number=None):
        return ' '.join(part for part in [doc_type.name, number] if part)

    @api.model
    def _get_expiry_folder(self, doc_type, record=None):
        """ :return: the folder of a new document of `doc_type` held by `record`: the folder of the type, else the
                     folder the record keeps its documents in, else the Expiring Documents folder """
        folder = doc_type.folder_id
        if not folder and record and hasattr(record, '_get_documents_folder'):
            folder = record.sudo()._get_documents_folder()
        if not folder:
            company = record.sudo().company_id if record and 'company_id' in record._fields else None
            folder = self._get_expiry_default_folder(company or self.env.company)
        return folder.with_env(self.env)

    @api.model
    def _get_expiry_default_folder(self, company):
        """ :return: the Expiring Documents folder; with several companies, its subfolder of `company`, so that
                     the documents belong to the company of their record """
        root = self.env.ref('om_document.folder_expiry', raise_if_not_found=False)
        if not root or root.sudo().company_id or self.env['res.company'].sudo().search_count([]) < 2:
            return root or self.env['om.documents.folder']
        Folder = self.env['om.documents.folder'].sudo().with_context(active_test=False)
        folder = Folder.search([('parent_id', '=', root.id), ('company_id', '=', company.id)], limit=1)
        if not folder:
            folder = Folder.create({
                'name': company.name,
                'parent_id': root.id,
                'company_id': company.id,
                'owner_id': root.owner_id.id,
                'access_internal': 'none',
            })
        return folder

    def _get_responsible_users(self):
        """ :return: who is reminded: the users the record names, else the responsible users of the type, else the
                     owner of the document """
        self.ensure_one()
        record = self._get_record()
        users = record.sudo()._document_responsible_users() if record and hasattr(
            record, '_document_responsible_users') else self.env['res.users']
        users = users or self.type_id.user_ids or self.owner_id
        return users.filtered(lambda user: user.active and not user.share)

    def _get_holder_partner(self):
        """ :return: the partner holding the document, emailed when its type notifies the holder: the one the
                     record names, else the contact of the document """
        self.ensure_one()
        record = self._get_record()
        partner = self.env['res.partner']
        if record and hasattr(record, '_document_holder_partner'):
            partner = record.sudo()._document_holder_partner()
        return partner or self.partner_id

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        Type = self.env['om.documents.type']
        context = self.env.context
        for vals in vals_list:
            doc_type = Type.browse(vals.get('type_id') or context.get('default_type_id'))
            if not doc_type:
                continue
            if not vals.get('name') and not context.get('default_name') and not vals.get('file_name') \
                    and not vals.get('attachment_id'):
                vals['name'] = self._get_expiry_name(doc_type, vals.get('number'))
            if not vals.get('folder_id') and not context.get('default_folder_id') \
                    and not context.get('om_documents_folder_id'):
                model = vals.get('res_model') or context.get('default_res_model')
                res_id = vals.get('res_id') or context.get('default_res_id')
                if vals.get('record_ref'):
                    model, res_id = vals['record_ref'].split(',')
                record = self.env[model].browse(int(res_id)).exists() if model in self.env and res_id else None
                folder = self._get_expiry_folder(doc_type, record)
                if folder:
                    vals['folder_id'] = folder.id
        documents = super().create(vals_list)
        # the renewal replaces the document it renews
        documents.previous_id.filtered('active').write({'active': False})
        return documents

    def write(self, vals):
        changed = self.browse()
        if 'date_expiry' in vals:
            changed = self.filtered(lambda d: d.date_expiry != fields.Date.to_date(vals['date_expiry']))
        result = super().write(vals)
        if changed:
            # a new expiry date is reminded of again
            super(DocumentsDocument, changed.sudo()).write({'last_reminder': -1})
        return result

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_renew(self):
        """ Open the document renewing this one: saving it archives this one. """
        self.ensure_one()
        if not self.type_id:
            raise UserError(self.env._('Give %s a document type first.', self.name))
        if self.next_id:
            raise UserError(self.env._('%(document)s is already renewed by %(renewal)s.', document=self.name,
                                       renewal=self.next_id.name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Renew %s', self.name),
            'res_model': self._name,
            'view_mode': 'form',
            'views': [(self.env.ref('om_document.om_documents_document_view_form_expiry').id, 'form')],
            'target': 'current',
            'context': {
                'default_res_model': self.res_model,
                'default_res_id': self.res_id,
                'default_type_id': self.type_id.id,
                'default_country_id': self.country_id.id,
                'default_folder_id': self.folder_id.id,
                'default_partner_id': self.partner_id.id,
                'default_tag_ids': self.tag_ids.ids,
                'default_previous_id': self.id,
                'default_name': self._get_expiry_name(self.type_id),
            },
        }

    def action_open_expiry_form(self):
        """ Open the document in the form of the expiring documents. """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('om_document.om_documents_document_view_form_expiry').id, 'form')],
        }

    # ------------------------------------------------------------------
    # Documents widget of the record holding them
    # ------------------------------------------------------------------

    def _expiry_board_values(self):
        self.ensure_one()
        files = self.attachment_id | self.extra_attachment_ids
        return {
            'id': self.id,
            'name': self.name,
            'type_id': self.type_id.id,
            'type_name': self.type_id.name,
            'number': self.number or '',
            'date_expiry': format_date(self.env, self.date_expiry) if self.date_expiry else '',
            'days_left': self.days_left,
            'state': self.expiry_state,
            'attachments': [{'id': attachment.id, 'name': attachment.name, 'mimetype': attachment.mimetype}
                            for attachment in files],
        }

    @api.model
    def expiry_board_data(self, res_model, res_id):
        """ :return: the typed documents of a record and the types it has no document of yet, for its widget """
        record = self.env[res_model].browse(res_id).exists()
        if not record or not self.has_access('read'):
            return {'documents': [], 'missing': [], 'can_edit': False}
        record.check_access('read')
        documents = self.search([('res_model', '=', res_model), ('res_id', '=', res_id), ('type_id', '!=', False)],
                                order='type_id, date_expiry desc, id desc')
        company = record.company_id if 'company_id' in record._fields and record.company_id else self.env.company
        types = self.env['om.documents.type'].search([
            ('res_model', '=', res_model), ('company_id', 'in', [False, company.id])])
        # a type is not missing when the record has a document of it in a folder the user does not reach
        kept_types = self.sudo().search([('res_model', '=', res_model), ('res_id', '=', res_id),
                                         ('type_id', 'in', types.ids)]).type_id
        return {
            'documents': [document._expiry_board_values() for document in documents],
            'missing': [{'id': doc_type.id, 'name': doc_type.name, 'description': doc_type.description or ''}
                        for doc_type in types - documents.type_id - kept_types],
            'can_edit': self.has_access('create'),
        }

    @api.model
    def expiry_board_upload(self, res_model, res_id, type_id, document_id, files):
        """ Attach files dropped on the widget: to the document, or to a new document of the type. The first file
        of a document without a file becomes its file, the others its extra files.

        :param files: list of dicts with the name, the mimetype and the base64 data of each file
        :return: the id of the document
        """
        if document_id:
            document = self.browse(document_id)
            document.check_access('write')
        else:
            self.env[res_model].browse(res_id).check_access('read')
            document = self.create({'res_model': res_model, 'res_id': res_id, 'type_id': type_id})
        document._expiry_add_files(files)
        return document.id

    def _expiry_add_files(self, files):
        """ Add files to the document: the first one is its file when it has none, the others its extra files. """
        self.ensure_one()
        attachments = self.env['ir.attachment'].create([{
            'name': file['name'],
            'mimetype': file.get('mimetype'),
            'raw': base64.b64decode(file['data']),
            'res_model': self._name,
            'res_id': self.id,
        } for file in files])
        if not self.attachment_id and self.type == 'binary' and attachments:
            self._set_file(attachments[0])
            attachments = attachments[1:]
        if attachments:
            self.extra_attachment_ids = [Command.link(attachment.id) for attachment in attachments]

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    def _get_due_reminder(self, today):
        """ :return: the reminder due today in days before the expiry, None when nothing is due """
        self.ensure_one()
        if not self.date_expiry or not self.type_id.has_expiry_date:
            return None
        days_left = (self.date_expiry - today).days
        due = [day for day in self.type_id._get_reminder_days() if days_left <= day]
        if not due:
            return None
        reminder = min(due)
        if self.last_reminder != -1 and reminder >= self.last_reminder:
            return None
        return reminder

    def _send_reminder(self, reminder):
        """ A to-do for each responsible user, and an email to the holder when the type asks for it. """
        self.ensure_one()
        days_left = (self.date_expiry - fields.Date.context_today(self)).days
        if days_left < 0:
            summary = self.env._('%s has expired', self.name)
        elif days_left == 0:
            summary = self.env._('%s expires today', self.name)
        else:
            summary = self.env._('%(document)s expires in %(days)s days', document=self.name, days=days_left)
        if self.res_name:
            summary = '%s: %s' % (self.res_name, summary)
        for user in self._get_responsible_users():
            self.activity_schedule('mail.mail_activity_data_todo', date_deadline=self.date_expiry,
                                   summary=summary, user_id=user.id)
        if self.type_id.notify_holder:
            partner = self._get_holder_partner()
            if partner.email:
                self.message_post(
                    body=self.env._('%(summary)s. Please renew it and send the new one.', summary=summary),
                    subject=summary, partner_ids=partner.ids, message_type='comment',
                    subtype_xmlid='mail.mt_comment')
        self.sudo().last_reminder = reminder

    @api.model
    def _cron_send_expiry_reminders(self):
        today = fields.Date.context_today(self)
        types = self.env['om.documents.type'].search([('has_expiry_date', '=', True)])
        horizon = today + timedelta(days=max([max(t._get_reminder_days() or [0]) for t in types] or [0]))
        documents = self.search([('type_id', 'in', types.ids), ('date_expiry', '!=', False),
                                 ('date_expiry', '<=', horizon)])
        for document in documents:
            reminder = document._get_due_reminder(today)
            if reminder is not None:
                document._send_reminder(reminder)
