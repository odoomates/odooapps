from odoo import _, fields, models


class IrActionsServer(models.Model):
    """ A server action that starts a workflow on its records: the action of
    the Automation Rule made for the Start of a workflow, or its entry in
    the Action menu. """
    _inherit = 'ir.actions.server'

    state = fields.Selection(selection_add=[('om_workflow', 'Start Workflow')],
                             ondelete={'om_workflow': 'cascade'})
    om_workflow_id = fields.Many2one('om.workflow', string='Workflow', ondelete='cascade', index='btree_not_null')

    def _run_action_om_workflow_multi(self, eval_context=None):
        records = eval_context.get('records') or eval_context.get('record')
        if not records:
            return False
        runs = self.om_workflow_id.sudo()._start_runs(records)
        if self.usage == 'base_automation':
            return False
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if runs else 'warning',
                'message': (_("Workflow %(workflow)s started on %(count)s records.",
                                       workflow=self.om_workflow_id.name, count=len(runs))
                            if runs else _("The workflow is already running on these records.")),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
