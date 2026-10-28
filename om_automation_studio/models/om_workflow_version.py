from odoo import _, api, fields, models


class OmWorkflowVersion(models.Model):
    """ A published graph of a workflow, frozen: the runs started on it keep
    following it when the workflow changes. """
    _name = 'om.workflow.version'
    _description = 'Workflow Version'
    _order = 'workflow_id, number desc'

    workflow_id = fields.Many2one('om.workflow', required=True, ondelete='cascade', index=True)
    number = fields.Integer(readonly=True)
    graph = fields.Json(readonly=True)
    run_count = fields.Integer(compute='_compute_run_count')

    def _compute_run_count(self):
        counts = dict(self.env['om.workflow.run']._read_group(
            [('version_id', 'in', self.ids)], ['version_id'], ['__count']))
        for version in self:
            version.run_count = counts.get(version, 0)

    @api.depends('number', 'workflow_id')
    def _compute_display_name(self):
        for version in self:
            version.display_name = _("%(workflow)s v%(number)s",
                                              workflow=version.workflow_id.name, number=version.number)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            last = self.search([('workflow_id', '=', vals['workflow_id'])], order='number desc', limit=1)
            vals['number'] = last.number + 1
        return super().create(vals_list)
