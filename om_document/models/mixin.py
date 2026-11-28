from odoo import fields, models


class DocumentsMixin(models.AbstractModel):
    """ For the models keeping their files in Documents, e.g. a project and its tasks, an employee: a Documents
    smart button, and the files attached to a record copied as documents in its folder.

    A model inheriting the mixin says in which folder in ``_get_documents_folder`` (nothing is copied while it gives
    none) and how the documents are filled in ``_get_documents_values``.
    """
    _name = 'om.documents.mixin'
    _description = 'Documents Mixin'

    om_documents_count = fields.Integer(string='Files in Documents', compute='_compute_om_documents_count')

    def _compute_om_documents_count(self):
        counts = dict(self.env['om.documents.document'].sudo()._read_group(
            [('res_model', '=', self._name), ('res_id', 'in', self.ids)], ['res_id'], ['__count']))
        for record in self:
            record.om_documents_count = counts.get(record.id, 0)

    def _get_documents_folder(self):
        """ :return: the folder of the documents of the record, empty to keep none """
        return self.env['om.documents.folder']

    def _get_documents_values(self):
        """ :return: more values of the documents made from the files of the record, e.g. the contact and tags """
        return {}

    def _om_documents_record_folder(self, parent, field_name, values=None):
        """ :return: the folder of the record kept in `field_name`, created in `parent` the first time """
        self.ensure_one()
        folder = self[field_name]
        if not folder and parent:
            company = self.company_id if 'company_id' in self._fields else self.env['res.company']
            folder = self.env['om.documents.folder'].sudo().create({
                'name': self.display_name,
                'parent_id': parent.id,
                'company_id': (company or parent.company_id).id,
                'owner_id': parent.owner_id.id,
                **(values or {}),
            })
            self.sudo()[field_name] = folder
        return folder

    def _om_documents_add_attachment(self, attachment):
        """ A document in the folder of the record from `attachment`, a file of the record, unless it has it """
        self.ensure_one()
        folder = self._get_documents_folder()
        if not folder:
            return self.env['om.documents.document']
        Document = self.env['om.documents.document'].sudo()
        if attachment.checksum and Document.with_context(active_test=False).search_count([
                ('res_model', '=', self._name), ('res_id', '=', self.id),
                ('attachment_id.checksum', '=', attachment.checksum)], limit=1):
            return Document
        copy = attachment.sudo().with_context(om_documents_no_sync=True).copy({
            'res_model': 'om.documents.document', 'res_id': 0})
        return Document.create({
            'name': attachment.name,
            'folder_id': folder.id,
            'attachment_id': copy.id,
            'res_model': self._name,
            'res_id': self.id,
            'owner_id': attachment.create_uid.id if attachment.create_uid._is_internal() else folder.owner_id.id,
            **self._get_documents_values(),
        })

    def action_open_om_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_document.action_documents')
        folder = self._get_documents_folder()
        action['domain'] = [('res_model', '=', self._name), ('res_id', '=', self.id)]
        action['context'] = {
            'default_res_model': self._name,
            'default_res_id': self.id,
            'om_documents_folder_id': folder.id,
            'searchpanel_default_folder_id': False,
        }
        action['display_name'] = self.env._('Documents of %s', self.display_name)
        return action
