from odoo import SUPERUSER_ID, models
from odoo.exceptions import UserError
from odoo.fields import Command


class DocumentsDocument(models.Model):
    _name = 'om.documents.document'
    _inherit = ['om.documents.document', 'sign.mixin']

    def _sign_default_signers(self):
        if self.partner_id:
            return [(1, self.env._('Signer'), self.partner_id)]
        return []

    def _create_sign_request(self):
        """ :return: a draft request to sign the PDF of the document, its contact suggested as the signer """
        self.ensure_one()
        if not self.attachment_id or not (self.mimetype or '').startswith('application/pdf'):
            raise UserError(self.env._('Only a PDF document can be sent for signature: %s is not one.', self.name))
        self.check_access('read')
        request = self.env['sign.request']._create_for_record(self, name=self.name)
        request.write({
            'document_file': self.attachment_id.sudo().raw,
            'document_filename': self.file_name or self.attachment_id.name,
        })
        if not request.signer_ids:
            request.signer_ids = [Command.create({'sequence': 1, 'role_name': self.env._('Signer')})]
        self.message_post(body=self.env._('Sent for signature: %s', request._get_html_link()),
                          subtype_xmlid='mail.mt_note')
        return request

    def action_request_signature(self):
        self.ensure_one()
        request = self._create_sign_request()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request',
            'res_id': request.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_request_signatures(self):
        requests = self.env['sign.request']
        for document in self:
            requests |= document._create_sign_request()
        if len(requests) == 1:
            return {'type': 'ir.actions.act_window', 'res_model': 'sign.request', 'res_id': requests.id,
                    'view_mode': 'form', 'views': [(False, 'form')]}
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Signature Requests'),
            'res_model': 'sign.request',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', requests.ids)],
        }

    def _on_sign_completed(self, request):
        """ The signed PDF becomes the new version of the document. """
        # the last signer is often the public user: the document changes in the name of who asked
        document = self.with_user(request.requested_by_id or SUPERUSER_ID).sudo()
        signed = request.sudo().signed_attachment_id
        if not signed:
            return
        copy = signed.with_context(om_documents_no_sync=True).copy(
            {'res_model': document._name, 'res_id': document.id})
        document._set_file(copy, version_note=self.env._('Before the signature of %s', request.reference))
        document.message_post(body=self.env._('Signed by everyone: the signed PDF is the new version.'),
                              subtype_xmlid='mail.mt_note')

    def _on_sign_declined(self, request):
        self.with_user(request.requested_by_id or SUPERUSER_ID).sudo().message_post(
            body=self.env._('The signature of %s was declined.', request.reference), subtype_xmlid='mail.mt_note')
