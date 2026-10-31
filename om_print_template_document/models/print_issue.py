from datetime import timedelta

from odoo import fields, models


class PrintIssue(models.Model):
    _inherit = 'print.issue'

    document_id = fields.Many2one('document.document', readonly=True, copy=False, check_company=True)

    def _on_issued(self):
        super()._on_issued()
        template = self.template_id
        if not template.document_type_id or not self.attachment_id:
            return
        # the document belongs to the record: whoever may print files it, whatever their rights on documents
        Document = self.env['document.document'].sudo()
        document = Document.create({
            'res_model': self.res_model,
            'res_id': self.res_id,
            'type_id': template.document_type_id.id,
            'name': '%s %s' % (template.document_type_id.name, self.name),
            'number': self.name,
            'date_issue': self.date,
            'date_expiry': self.date + timedelta(days=template.validity_days) if template.validity_days else False,
            'company_id': self.company_id.id,
        })
        attachment = self.attachment_id.sudo().copy({'res_model': Document._name, 'res_id': document.id})
        document.attachment_ids = [fields.Command.link(attachment.id)]
        self.document_id = document

    def _on_cancelled(self):
        result = super()._on_cancelled()
        self.document_id.sudo().active = False
        return result
