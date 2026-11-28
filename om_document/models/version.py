from odoo import api, fields, models
from odoo.tools.misc import human_size


class DocumentsVersion(models.Model):
    """ A previous file of a document, replaced by a newer version and kept to be restored. """
    _name = 'om.documents.version'
    _description = 'Document Version'
    _order = 'id desc'

    document_id = fields.Many2one('om.documents.document', string='Document', required=True, index=True,
                                  ondelete='cascade')
    attachment_id = fields.Many2one('ir.attachment', string='File', required=True, ondelete='cascade')
    name = fields.Char(related='attachment_id.name', string='File Name')
    mimetype = fields.Char(related='attachment_id.mimetype', string='File Type')
    file_size = fields.Integer(related='attachment_id.file_size', string='Size')
    file_size_human = fields.Char(string='File Size', compute='_compute_file_size_human')
    uploaded_by_id = fields.Many2one(related='attachment_id.create_uid', string='Uploaded By')
    date_uploaded = fields.Datetime(related='attachment_id.create_date', string='Uploaded On')
    note = fields.Char()

    @api.depends('file_size')
    def _compute_file_size_human(self):
        for version in self:
            version.file_size_human = human_size(version.file_size)

    def action_restore(self):
        self.ensure_one()
        self.document_id.check_access('write')
        self.document_id._restore_version(self)
        return {'type': 'ir.actions.act_window_close'}

    def action_download(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % self.attachment_id.id,
                'target': 'download'}
