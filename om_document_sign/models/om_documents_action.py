from odoo import fields, models


class DocumentsAction(models.Model):
    _inherit = 'om.documents.action'

    create_model = fields.Selection(selection_add=[('sign_request', 'Signature Request')],
                                    ondelete={'sign_request': 'set default'})

    def _create_records_sign_request(self, documents):
        requests = self.env['sign.request']
        for document in documents:
            requests |= document._create_sign_request()
        return requests
