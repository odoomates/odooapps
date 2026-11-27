from odoo import fields, models


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'om.documents.mixin']

    om_documents_folder_id = fields.Many2one('om.documents.folder', string='Documents Folder', copy=False,
                                             index='btree_not_null', ondelete='set null')

    def _get_documents_folder(self):
        root = self.env.ref('om_documents_product.folder_products', raise_if_not_found=False)
        return self._om_documents_record_folder(root, 'om_documents_folder_id')

    def write(self, vals):
        result = super().write(vals)
        if 'name' in vals:
            for template in self.filtered('om_documents_folder_id'):
                template.om_documents_folder_id.sudo().name = template.display_name
        return result
