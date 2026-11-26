from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    is_field_service = fields.Boolean(
        string="Field Service",
        help="The tasks of this project are field service jobs: planned on technicians, done at the "
             "customer site, with travel and work time, checklist, signature and job report.")

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if self.env.context.get('default_is_field_service'):
            res.setdefault('allow_timesheets', True)
        return res

    def action_view_fs_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id}
        action['name'] = self.name
        return action
