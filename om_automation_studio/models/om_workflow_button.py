import json

from odoo import api, models
from odoo.tools import ormcache

from odoo.addons.om_automation_studio.tools import eval_domain


class OmWorkflow(models.Model):
    """ A workflow that starts on a button: the button goes on only once the
    approvals of the workflow are given. Clicking it asks them; clicking it
    again, once approved, goes on. A change of what was approved asks again. """
    _inherit = 'om.workflow'

    @api.model
    @ormcache()
    def _button_workflows(self):
        """ The published workflows that start on a button, by (model, method). """
        result = {}
        for workflow in self.sudo().search([('state', '=', 'active')]):
            config = (self._start_node(workflow.version_id.graph) or {}).get('config') or {}
            if config.get('trigger') == 'button' and config.get('method'):
                result.setdefault((workflow.model, config['method']), []).append(workflow.id)
        return {key: tuple(ids) for key, ids in result.items()}

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    @api.model
    def _button_gate(self, model, method, ids):
        """ What the click of the button ``method`` on the records ``ids`` of
        ``model`` may do.

        :return: None when no workflow waits on the button, else the ids
            that go on and the messages about the others
        """
        workflow_ids = self._button_workflows().get((model, method))
        if not workflow_ids or model not in self.env:
            return None
        records = self.env[model].browse(ids).exists()
        blocked = records.browse()
        messages = []
        for workflow in self.sudo().browse(workflow_ids).exists().filtered(lambda w: w.state == 'active'):
            config = (workflow._start_node(workflow.version_id.graph) or {}).get('config') or {}
            domain = eval_domain(self.env, config.get('domain'))
            for record in (records - blocked).sudo().filtered_domain(domain):
                message = workflow._button_check(record, config)
                if message:
                    blocked |= record
                    messages.append(message)
        if not blocked:
            return None
        return (records - blocked).ids, messages

    def _button_check(self, record, config):
        """ Why ``record`` cannot go on yet, or False when it can. """
        self.ensure_one()
        values = self._button_values(record, config)
        run = self.env['om.workflow.run'].sudo().search([
            ('workflow_id', '=', self.id), ('res_id', '=', record.id), ('button_values', '!=', False),
        ], limit=1)
        if run:
            verdict = run._button_verdict()
            if verdict == 'pending':
                return run._button_message(verdict)
            if verdict == 'ok' and run.button_values == values:
                return False
        run = self._start_runs(record, button_values=values)
        verdict = run._button_verdict() if run else 'ok'
        return False if verdict == 'ok' else run._button_message(verdict, asked=True)

    def _button_values(self, record, config):
        """ What an approval of ``record`` covers: the fields of the condition
        of the Start, and the fields it watches. """
        paths = [leaf[0] for leaf in eval_domain(self.env, config.get('domain'))
                 if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and isinstance(leaf[0], str)]
        paths += config.get('fields') or []
        values = {}
        for path in sorted(set(paths)):
            try:
                value = record.sudo().mapped(path)
            except (KeyError, ValueError, AttributeError):
                continue
            values[path] = value.ids if isinstance(value, models.BaseModel) else value
        return json.dumps(values, sort_keys=True, default=str)

