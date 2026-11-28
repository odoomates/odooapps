from datetime import timedelta

from odoo import fields, models


class PrintIssue(models.Model):
    _inherit = 'print.issue'

    document_id = fields.Many2one('om.documents.document', readonly=True, copy=False, check_company=True)

    def _on_issued(self):
        super()._on_issued()
        template = self.template_id
        if not template.document_type_id or not self.attachment_id:
            return
        # the document belongs to the record: whoever may print files it, whatever their rights on documents; it
        # goes to the folder of its type, else of its record, in the company of the print
        Document = self.env['om.documents.document'].sudo().with_company(self.company_id)
        document = Document.create({
            'res_model': self.res_model,
            'res_id': self.res_id,
            'type_id': template.document_type_id.id,
            'name': '%s %s' % (template.document_type_id.name, self.name),
            'number': self.name,
            'date_issue': self.date,
            'date_expiry': self.date + timedelta(days=template.validity_days) if template.validity_days else False,
            # the document keeps a copy of the PDF of the print
            'attachment_id': self.attachment_id.id,
        })
        self.document_id = document

    def _on_cancelled(self):
        result = super()._on_cancelled()
        self.document_id.sudo().active = False
        return result
