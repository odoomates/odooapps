from odoo import api, fields, models
from odoo.fields import Command


class DocumentsRequestWizard(models.TransientModel):
    """ Ask a contact for a document: a missing document waits in the folder, the contact gets a link to upload
    it, and the user an activity until it arrives. """
    _name = 'om.documents.request.wizard'
    _description = 'Request a Document'

    name = fields.Char(string='Document', required=True, help='What is asked, e.g. "Signed contract".')
    partner_id = fields.Many2one('res.partner', string='Ask', required=True)
    folder_id = fields.Many2one('om.documents.folder', string='Folder', required=True,
                                default=lambda self: self.env['om.documents.document']._default_folder())
    tag_ids = fields.Many2many('om.documents.tag', string='Tags')
    user_id = fields.Many2one('res.users', string='Followed By', required=True, default=lambda self: self.env.user,
                              domain=[('share', '=', False)])
    deadline = fields.Date(string='Needed By', default=lambda self: fields.Date.add(fields.Date.today(), days=7))
    message = fields.Text(help='Added to the email sent to the contact.')
    res_model = fields.Char()
    res_id = fields.Integer()

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        context = self.env.context
        if context.get('active_model') and context.get('active_model') != 'om.documents.document' \
                and context.get('active_id') and 'res_model' in fields:
            values.setdefault('res_model', context['active_model'])
            values.setdefault('res_id', context['active_id'])
        return values

    def action_request(self):
        self.ensure_one()
        self.folder_id.check_access('write')
        document = self.env['om.documents.document'].create({
            'name': self.name,
            'folder_id': self.folder_id.id,
            'partner_id': self.partner_id.id,
            'owner_id': self.user_id.id,
            'tag_ids': [Command.set(self.tag_ids.ids)],
            'is_request': True,
            'request_deadline': self.deadline,
            'res_model': self.res_model or False,
            'res_id': self.res_id or False,
        })
        share = self.env['om.documents.share'].create({
            'name': self.env._('Request: %s', self.name),
            'share_type': 'documents',
            'folder_id': self.folder_id.id,
            'document_ids': [Command.set(document.ids)],
            'request_document_id': document.id,
            'allow_download': False,
            'allow_upload': True,
            'upload_tag_ids': [Command.set(self.tag_ids.ids)],
            'upload_owner_id': self.user_id.id,
            'partner_ids': [Command.set(self.partner_id.ids)],
        })
        document.activity_schedule(
            'om_documents.mail_activity_type_request',
            date_deadline=self.deadline or fields.Date.context_today(self),
            summary=self.env._('%(document)s from %(partner)s', document=self.name, partner=self.partner_id.name),
            user_id=self.user_id.id)
        share.message_post_with_source(
            'om_documents.message_document_request',
            render_values={'share': share, 'document': document, 'message': self.message,
                           'deadline': self.deadline},
            subtype_xmlid='mail.mt_comment', message_type='comment', partner_ids=self.partner_id.ids,
            subject=self.env._('Document requested: %s', self.name))
        document.message_post(body=self.env._('Requested from %s.', self.partner_id.name),
                              subtype_xmlid='mail.mt_note')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.documents.document',
            'res_id': document.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
