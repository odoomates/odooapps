from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DocumentsType(models.Model):
    """ A kind of document with an expiry, e.g. the passport of an employee or the trade license of the company. """
    _name = 'om.documents.type'
    _description = 'Document Type'
    _order = 'sequence, name, id'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help='Identifies the type in code and in the data of the other modules, e.g. PASSPORT.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', string='Applies To', ondelete='cascade', index=True, domain=[('transient', '=', False)],
        help='The kind of record the documents of this type belong to, e.g. Employee. Leave empty for documents '
             'kept in a folder only, e.g. the trade license of the company.')
    res_model = fields.Char(related='model_id.model', store=True, index=True, string='Model')
    has_number = fields.Boolean(string='Has a Number', default=True)
    has_issue_date = fields.Boolean(string='Has an Issue Date', default=True)
    has_expiry_date = fields.Boolean(string='Expires', default=True)
    reminder_days = fields.Char(
        string='Remind', default='30,7,0',
        help='The days before the expiry date to remind on, separated by commas. 0 reminds on the day it expires. '
             'Each reminder is sent once.')
    notify_holder = fields.Boolean(
        string='Notify the Holder',
        help='Also email the holder of the document, e.g. the employee whose passport is about to expire.')
    user_ids = fields.Many2many(
        'res.users', 'om_documents_type_user_rel', 'type_id', 'user_id', string='Responsible Users',
        domain=[('share', '=', False)],
        help='Reminded when the record of the document names no one responsible.')
    folder_id = fields.Many2one(
        'om.documents.folder', string='Folder', check_company=True, ondelete='set null',
        help='Where the new documents of this type are kept. Empty: the folder of their record, else the Expiring '
             'Documents folder.')
    company_id = fields.Many2one('res.company', index=True,
                                 help='Leave empty to share the type with all the companies.')
    description = fields.Text(help='Explains the document to the people filling it in.')
    document_count = fields.Integer(compute='_compute_document_count', string='Documents')

    _code_uniq = models.Constraint('UNIQUE(code, model_id, company_id)',
                                   'A code is used once per kind of record and company.')

    @api.constrains('reminder_days')
    def _check_reminder_days(self):
        for doc_type in self:
            try:
                doc_type._get_reminder_days()
            except ValueError:
                raise ValidationError(self.env._(
                    'Remind of %s takes numbers of days separated by commas, e.g. 30,7,0.', doc_type.name)) from None

    def _compute_document_count(self):
        Document = self.env['om.documents.document']
        counts = dict(Document._read_group([('type_id', 'in', self.ids)], ['type_id'], ['__count'])) \
            if Document.has_access('read') else {}
        for doc_type in self:
            doc_type.document_count = counts.get(doc_type, 0)

    def _get_reminder_days(self):
        """ :return: the days before the expiry to remind on, the earliest reminder first, e.g. [30, 7, 0] """
        self.ensure_one()
        days = {int(day) for day in (self.reminder_days or '').split(',') if day.strip()}
        if any(day < 0 for day in days):
            raise ValueError('negative reminder')
        return sorted(days, reverse=True)

    def action_open_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_documents_expiry.action_expiry_documents')
        action['domain'] = [('type_id', '=', self.id)]
        action['context'] = {'default_type_id': self.id}
        action['display_name'] = self.name
        return action
