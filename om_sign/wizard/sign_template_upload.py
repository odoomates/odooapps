import os

from odoo import fields, models
from odoo.exceptions import UserError

from ..models.sign_template import pdf_page_count


class SignTemplateUpload(models.TransientModel):
    """ A PDF uploaded becomes a sign template, opened in the editor to place its fields. """
    _name = 'sign.template.upload'
    _description = 'Upload a PDF to Sign'

    document_file = fields.Binary(string='PDF', required=True)
    document_filename = fields.Char()
    name = fields.Char(help='By default, the name of the file.')

    def action_upload(self):
        self.ensure_one()
        data = self.document_file.content if self.document_file else b''
        if not pdf_page_count(data):
            raise UserError(self.env._('Upload a PDF file.'))
        filename = self.document_filename or 'document.pdf'
        name = (self.name or '').strip() or os.path.splitext(filename)[0] or filename
        template = self.env['sign.template'].create({
            'name': name,
            'document_file': self.document_file,
            'document_filename': filename,
            'role_ids': [fields.Command.create({'name': self.env._('Customer'), 'sequence': 10, 'color': 1})],
        })
        return template.action_open_editor()
