from odoo import api, models


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _om_documents_claim(self, document):
        """ Make the attachment the file of `document`: it moves to the document when it is attached to nothing
        yet, and is copied when it belongs to another record. """
        self.ensure_one()
        if self.res_model == document._name and self.res_id == document.id:
            return self
        if not self.res_model or (self.res_model == document._name and not self.res_id):
            self.sudo().write({'res_model': document._name, 'res_id': document.id, 'res_field': False})
            return self
        self.check_access('read')
        copy = self.sudo().with_context(om_documents_no_sync=True).copy(
            {'res_model': document._name, 'res_id': document.id})
        document.sudo().attachment_id = copy
        return copy

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        if not self.env.context.get('om_documents_no_sync'):
            attachments._om_documents_sync()
        return attachments

    def _om_documents_sync(self):
        """ The files attached to a record keeping documents (see om.documents.mixin) are copied in its folder. """
        Mixin = self.pool['om.documents.mixin']
        for attachment in self:
            model = attachment.res_model
            if not model or not attachment.res_id or attachment.res_field or attachment.type != 'binary' \
                    or model not in self.env or not isinstance(self.env[model], Mixin):
                continue
            record = self.env[model].browse(attachment.res_id).exists()
            if record:
                record.sudo()._om_documents_add_attachment(attachment)
