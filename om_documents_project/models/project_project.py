from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class ProjectProject(models.Model):
    _name = 'project.project'
    _inherit = ['project.project', 'om.documents.mixin']

    use_om_documents = fields.Boolean(string='Keep Files in Documents', default=True,
                                      help='Keep the files of the project and its tasks in a folder of Documents.')
    om_documents_folder_id = fields.Many2one('om.documents.folder', string='Documents Folder', copy=False,
                                             index='btree_not_null', ondelete='set null')

    def _get_documents_folder(self):
        if not self.use_om_documents or self.is_template:
            return self.env['om.documents.folder']
        root = self.env.ref('om_documents_project.folder_projects', raise_if_not_found=False)
        return self._om_documents_record_folder(root, 'om_documents_folder_id')

    def _get_documents_values(self):
        return {'partner_id': self.partner_id.id} if self.partner_id else {}

    def _compute_om_documents_count(self):
        # the documents of the folder of the project, those of its tasks included
        folders = self.om_documents_folder_id
        counts = dict(self.env['om.documents.document'].sudo()._read_group(
            [('folder_id', 'child_of', folders.ids)], ['folder_id'], ['__count'])) if folders else {}
        for project in self:
            project.om_documents_count = sum(
                count for folder, count in counts.items()
                if project.om_documents_folder_id and folder.parent_path.startswith(
                    project.om_documents_folder_id.parent_path))

    def action_open_om_documents(self):
        self.ensure_one()
        action = super().action_open_om_documents()
        folder = self._get_documents_folder()
        if folder:
            action['domain'] = [('folder_id', 'child_of', folder.id)]
            action['context'] = dict(action['context'], default_res_model=False, default_res_id=False)
        return action

    def write(self, vals):
        result = super().write(vals)
        if 'name' in vals:
            for project in self.filtered('om_documents_folder_id'):
                project.om_documents_folder_id.sudo().name = project.name
        return result

    def action_share_om_documents(self):
        """ Share the folder of the project with its customer: they find it in their portal. """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(self.env._('Set the customer of %s to share its documents with.', self.name))
        folder = self._get_documents_folder()
        if not folder:
            raise UserError(self.env._('%s keeps no documents.', self.name))
        share = self.env['om.documents.share'].create({
            'name': self.name,
            'share_type': 'folder',
            'folder_id': folder.id,
            'include_subfolders': True,
            'partner_ids': [Command.set(self.partner_id.ids)],
        })
        return share._action_open()
