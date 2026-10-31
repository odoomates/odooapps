import base64
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools.misc import format_date


class Document(models.Model):
    """ A document kept on any record, e.g. a passport on an employee, with its expiry date and its reminders.

    The record holding it may inherit ``document.mixin`` to say who is reminded and who holds the document.
    """
    _name = 'document.document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Document'
    _check_company_auto = True
    _order = 'date_expiry, id desc'
    _mail_post_access = 'read'

    name = fields.Char(compute='_compute_name', store=True, readonly=False, required=True, precompute=True)
    active = fields.Boolean(default=True)
    res_model = fields.Char(string='Model', required=True, index=True)
    res_id = fields.Many2oneReference(string='Record ID', model_field='res_model', required=True, index=True)
    res_name = fields.Char(string='Holder', compute='_compute_res_name')
    record_ref = fields.Reference(selection='_selection_record_ref', string='Belongs To',
                                  compute='_compute_record_ref', inverse='_inverse_record_ref')
    type_id = fields.Many2one(
        'document.type', required=True, tracking=True, index=True, check_company=True,
        domain="[('res_model', '=', res_model)]")
    has_number = fields.Boolean(related='type_id.has_number')
    has_issue_date = fields.Boolean(related='type_id.has_issue_date')
    has_expiry_date = fields.Boolean(related='type_id.has_expiry_date')
    number = fields.Char(tracking=True)
    date_issue = fields.Date(string='Issued On', tracking=True)
    date_expiry = fields.Date(string='Expires On', tracking=True, index=True)
    country_id = fields.Many2one('res.country', string='Issued By')
    attachment_ids = fields.Many2many('ir.attachment', 'om_document_attachment_rel', 'document_id',
                                      'attachment_id', string='Files')
    preview_url = fields.Char(compute='_compute_preview')
    attachment_count = fields.Integer(string='File Count', compute='_compute_preview')
    note = fields.Text()
    company_id = fields.Many2one('res.company', required=True, index=True,
                                 default=lambda self: self.env.company)
    state = fields.Selection([
        ('none', 'No Expiry'),
        ('valid', 'Valid'),
        ('expiring', 'Expiring'),
        ('expired', 'Expired'),
    ], compute='_compute_state', search='_search_state',
        help='Expiring: the first reminder of its type is due.')
    days_left = fields.Integer(compute='_compute_state')
    last_reminder = fields.Integer(
        copy=False, default=-1,
        help='The reminder sent last, in days before the expiry date, -1 for none: each one is sent once.')
    previous_id = fields.Many2one('document.document', string='Renews', copy=False, readonly=True, index=True,
                                  check_company=True)
    renewal_ids = fields.One2many('document.document', 'previous_id', string='Renewals', context={'active_test': False})
    next_id = fields.Many2one('document.document', string='Renewed By', compute='_compute_next_id')

    @api.depends('type_id', 'number')
    def _compute_name(self):
        for document in self:
            parts = [document.type_id.name, document.number]
            document.name = ' '.join(part for part in parts if part) or document.name

    @api.depends('attachment_ids')
    def _compute_preview(self):
        for document in self:
            images = document.attachment_ids.filtered(lambda a: (a.mimetype or '').startswith('image/'))
            document.preview_url = '/web/image/%s/320x200' % images[0].id if images else False
            document.attachment_count = len(document.attachment_ids)

    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for document in self:
            record = document._get_record()
            document.res_name = record.sudo().display_name if record else False

    @api.model
    def _selection_record_ref(self):
        """ The kinds of record a document type is kept on. """
        models_ = self.env['document.type'].sudo().with_context(active_test=False).search(
            [('model_id', '!=', False)]).model_id
        return [(model.model, model.name) for model in models_]

    @api.depends('res_model', 'res_id')
    def _compute_record_ref(self):
        selection = {model for model, _name in self._selection_record_ref()}
        for document in self:
            document.record_ref = '%s,%s' % (document.res_model, document.res_id) \
                if document.res_model in selection and document.res_id else False

    @api.onchange('record_ref')
    def _onchange_record_ref(self):
        if self.record_ref:
            self.res_model, self.res_id = self.record_ref._name, self.record_ref.id

    def _inverse_record_ref(self):
        for document in self.filtered('record_ref'):
            document.write({'res_model': document.record_ref._name, 'res_id': document.record_ref.id})

    @api.depends('date_expiry', 'type_id.has_expiry_date', 'type_id.reminder_days')
    @api.depends_context('date')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for document in self:
            if not document.date_expiry or not document.type_id.has_expiry_date:
                document.state, document.days_left = 'none', 0
                continue
            document.days_left = (document.date_expiry - today).days
            if document.days_left < 0:
                document.state = 'expired'
            elif document.days_left <= max(document.type_id._get_reminder_days() or [0]):
                document.state = 'expiring'
            else:
                document.state = 'valid'

    def _search_state(self, operator, value):
        if operator != 'in':
            return NotImplemented
        today = fields.Date.context_today(self)
        expiring_ids = []
        for doc_type in self.env['document.type'].with_context(active_test=False).search(
                [('has_expiry_date', '=', True)]):
            horizon = today + timedelta(days=max(doc_type._get_reminder_days() or [0]))
            expiring_ids += self.sudo().with_context(active_test=False).search([
                ('type_id', '=', doc_type.id), ('date_expiry', '>=', today), ('date_expiry', '<=', horizon)]).ids
        domains = {
            'none': Domain('date_expiry', '=', False) | Domain('type_id.has_expiry_date', '=', False),
            'expired': Domain('date_expiry', '<', today) & Domain('type_id.has_expiry_date', '=', True),
            'expiring': Domain('id', 'in', expiring_ids),
            'valid': Domain('date_expiry', '>=', today) & Domain('type_id.has_expiry_date', '=', True)
                     & Domain('id', 'not in', expiring_ids),
        }
        return Domain.OR(domains[state] for state in value if state in domains)

    @api.depends('renewal_ids')
    def _compute_next_id(self):
        for document in self:
            document.next_id = document.with_context(active_test=False).renewal_ids[:1]

    @api.constrains('date_issue', 'date_expiry')
    def _check_dates(self):
        for document in self:
            if document.date_issue and document.date_expiry and document.date_expiry < document.date_issue:
                raise ValidationError(self.env._('%s expires before it is issued.', document.name))

    @api.constrains('res_model', 'type_id')
    def _check_type(self):
        for document in self:
            if document.type_id.res_model != document.res_model:
                raise ValidationError(self.env._('A %(type)s is not kept on a %(model)s.', type=document.type_id.name,
                                                 model=self.env['ir.model']._get(document.res_model).name))

    # ------------------------------------------------------------------
    # Record holding the document
    # ------------------------------------------------------------------

    def _get_record(self):
        """ :return: the record the document belongs to, empty when it no longer exists """
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env or not self.res_id:
            return None
        return self.env[self.res_model].browse(self.res_id).exists()

    def _get_responsible_users(self):
        """ :return: who is reminded: the users the record names, else the responsible users of the type """
        self.ensure_one()
        record = self._get_record()
        users = record.sudo()._document_responsible_users() if record and hasattr(
            record, '_document_responsible_users') else self.env['res.users']
        return (users or self.type_id.user_ids).filtered(lambda user: user.active and not user.share)

    def _get_holder_partner(self):
        """ :return: the partner holding the document, emailed when its type notifies the holder """
        self.ensure_one()
        record = self._get_record()
        if record and hasattr(record, '_document_holder_partner'):
            return record.sudo()._document_holder_partner()
        return self.env['res.partner']

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('record_ref'):
                model, res_id = vals.pop('record_ref').split(',')
                vals.update(res_model=model, res_id=int(res_id))
            record = self.env[vals['res_model']].browse(vals['res_id']) if vals.get('res_model') else None
            if record and 'company_id' not in vals and 'company_id' in record._fields and record.company_id:
                vals['company_id'] = record.sudo().company_id.id
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
            super(Document, changed.sudo()).write({'last_reminder': -1})
        return result

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_renew(self):
        """ Open the document renewing this one: saving it archives this one. """
        self.ensure_one()
        if self.next_id:
            raise UserError(self.env._('%(document)s is already renewed by %(renewal)s.', document=self.name,
                                       renewal=self.next_id.name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Renew %s', self.name),
            'res_model': 'document.document',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'default_res_model': self.res_model,
                'default_res_id': self.res_id,
                'default_type_id': self.type_id.id,
                'default_country_id': self.country_id.id,
                'default_company_id': self.company_id.id,
                'default_previous_id': self.id,
            },
        }

    def action_open_record(self):
        self.ensure_one()
        record = self._get_record()
        if not record:
            raise UserError(self.env._('The record of %s no longer exists.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    # ------------------------------------------------------------------
    # Documents widget of the record holding them
    # ------------------------------------------------------------------

    def _board_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'type_id': self.type_id.id,
            'type_name': self.type_id.name,
            'number': self.number or '',
            'date_expiry': format_date(self.env, self.date_expiry) if self.date_expiry else '',
            'days_left': self.days_left,
            'state': self.state,
            'attachments': [{'id': attachment.id, 'name': attachment.name, 'mimetype': attachment.mimetype}
                            for attachment in self.attachment_ids],
        }

    @api.model
    def board_data(self, res_model, res_id):
        """ :return: the documents of a record and the types it has no document of yet, for its widget """
        record = self.env[res_model].browse(res_id).exists()
        if not record:
            return {'documents': [], 'missing': [], 'can_edit': False}
        record.check_access('read')
        documents = self.search([('res_model', '=', res_model), ('res_id', '=', res_id)],
                                order='type_id, date_expiry desc, id desc')
        company = record.company_id if 'company_id' in record._fields and record.company_id else self.env.company
        types = self.env['document.type'].search([
            ('res_model', '=', res_model), '|', ('company_id', '=', False), ('company_id', '=', company.id)])
        return {
            'documents': [document._board_values() for document in documents],
            'missing': [{'id': doc_type.id, 'name': doc_type.name, 'description': doc_type.description or ''}
                        for doc_type in types - documents.type_id],
            'can_edit': self.has_access('create'),
        }

    @api.model
    def board_upload(self, res_model, res_id, type_id, document_id, files):
        """ Attach files dropped on the widget: to the document, or to a new document of the type.

        :param files: list of dicts with the name, the mimetype and the base64 data of each file
        :return: the id of the document
        """
        if document_id:
            document = self.browse(document_id)
            document.check_access('write')
        else:
            document = self.create({'res_model': res_model, 'res_id': res_id, 'type_id': type_id})
        attachments = self.env['ir.attachment'].create([{
            'name': file['name'],
            'mimetype': file.get('mimetype'),
            'raw': base64.b64decode(file['data']),
            'res_model': self._name,
            'res_id': document.id,
        } for file in files])
        document.attachment_ids = [fields.Command.link(attachment.id) for attachment in attachments]
        return document.id

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
    def _cron_send_reminders(self):
        today = fields.Date.context_today(self)
        types = self.env['document.type'].search([('has_expiry_date', '=', True)])
        horizon = today + timedelta(days=max([max(t._get_reminder_days() or [0]) for t in types] or [0]))
        documents = self.search([('type_id', 'in', types.ids), ('date_expiry', '!=', False),
                                 ('date_expiry', '<=', horizon)])
        for document in documents:
            reminder = document._get_due_reminder(today)
            if reminder is not None:
                document._send_reminder(reminder)
