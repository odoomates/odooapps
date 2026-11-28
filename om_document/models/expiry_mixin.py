from odoo import api, fields, models


class DocumentsExpiryMixin(models.AbstractModel):
    """ A record holding expiring documents, e.g. an employee with a passport and a work permit.

    It keeps its files in Documents like any ``om.documents.mixin`` model, and adds its typed documents: their
    count, the count to renew, and the Documents widget (``widget="om_documents_expiry_board"`` on
    ``document_ids``). A model inheriting it names who is reminded of the expiring documents in
    ``_document_responsible_users`` and who holds them in ``_document_holder_partner``.
    """
    _name = 'om.documents.expiry.mixin'
    _inherit = ['om.documents.mixin']
    _description = 'Documents Expiry Mixin'

    document_ids = fields.One2many(
        'om.documents.document', 'res_id', string='Documents',
        domain=lambda self: [('res_model', '=', self._name), ('type_id', '!=', False)],
        groups='om_document.group_documents_user')
    document_count = fields.Integer(compute='_compute_document_count', groups='om_document.group_documents_user')
    document_alert_count = fields.Integer(string='Documents to Renew', compute='_compute_document_count',
                                          groups='om_document.group_documents_user',
                                          help='The documents expiring or expired.')

    @api.depends('document_ids')
    def _compute_document_count(self):
        Document = self.env['om.documents.document']
        domain = [('res_model', '=', self._name), ('res_id', 'in', self.ids), ('type_id', '!=', False)]
        counts = dict(Document._read_group(domain, ['res_id'], ['__count']))
        alerts = dict(Document._read_group(
            domain + [('expiry_state', 'in', ['expiring', 'expired'])], ['res_id'], ['__count']))
        for record in self:
            record.document_count = counts.get(record.id, 0)
            record.document_alert_count = alerts.get(record.id, 0)

    def _document_responsible_users(self):
        """ :return: the users reminded of the documents of the record, empty for the users of the type """
        return self.env['res.users']

    def _document_holder_partner(self):
        """ :return: the partner holding the documents of the record, emailed when the type notifies the holder """
        return self.env['res.partner']

    def action_open_documents(self):
        """ The typed documents of the record, in the views of the expiring documents. """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_document.action_expiry_documents')
        action['display_name'] = self.env._('Documents of %s', self.display_name)
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id), ('type_id', '!=', False)]
        action['context'] = {
            'default_res_model': self._name,
            'default_res_id': self.id,
        }
        return action

    def unlink(self):
        documents = self.env['om.documents.document'].sudo().with_context(active_test=False).search(
            [('res_model', '=', self._name), ('res_id', 'in', self.ids), ('type_id', '!=', False)])
        result = super().unlink()
        documents.unlink()
        return result
