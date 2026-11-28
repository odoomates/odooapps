from odoo import models


class ProjectTask(models.Model):
    _name = 'project.task'
    _inherit = ['project.task', 'om.documents.mixin']

    def _get_documents_folder(self):
        if not self.project_id:
            return self.env['om.documents.folder']
        return self.project_id._get_documents_folder()

    def _get_documents_values(self):
        partner = self.partner_id or self.project_id.partner_id
        return {'partner_id': partner.id} if partner else {}
